"""Interactive chat pop-up application using local Ollama.

Supports document ingestion into ChromaDB and retrieval-augmented generation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import chromadb
import langid
from langchain_community.document_loaders import PyPDFLoader
from ollama import Client

from gemini_application.application_abstract import ApplicationAbstract

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ChunkRecord:
    """A single text chunk with id and metadata for storage and citation."""

    chunk_id: str
    text: str
    metadata: Dict[str, Any]


class ChatPopup(ApplicationAbstract):
    """Retrieval-augmented chat application built on ChromaDB + Ollama."""

    def __init__(self):
        """Initialize configuration fields; actual clients are created in initialize_model()."""
        super().__init__()

        # Ollama client (created in initialize_model)
        self.ollama_client: Optional[Client] = None

        # Ollama embedding model name
        self.ollama_embeddings_model: Optional[str] = None

        # Ollama generation model name
        self.ollama_llm_model: Optional[str] = None

        # Ollama server host
        self.ollama_host: Optional[str] = None

        # Ollama server port
        self.ollama_port: Optional[int] = None

        # Chroma client object (created in initialize_model)
        self.chroma_client = None

        # Chroma collection handle (created in initialize_model)
        self.chroma_collection = None

        # Chroma server host (used when chromadb_use_http=True)
        self.chromadb_host: Optional[str] = None

        # Chroma server port (used when chromadb_use_http=True)
        self.chromadb_port: Optional[int] = None

        # Chroma collection name
        self.collection_name: Optional[str] = None

        # Use Chroma via HTTP (True) or local persistent storage (False)
        self.chromadb_use_http: bool = True

        # Local Chroma persistence directory (used when chromadb_use_http=False)
        self.chroma_dir: Optional[str] = None

        # Directory containing documents to ingest
        self.docs_dir: Optional[str] = None

        # Optional prompt template (the class uses a built-in strict RAG prompt by default)
        self.prompt: Optional[str] = None

        # Chunk size for general use (words)
        self.chunk_size: int = 200

        # Chunk overlap for general use (words)
        self.chunk_overlap: int = 40

        # Chunk size for embedding (words; conservative for embedding context limits)
        self.embedding_chunk_size: int = 120

        # Chunk overlap for embedding (words)
        self.embedding_chunk_overlap: int = 20

        # Minimum similarity needed to keep a retrieved chunk (cosine similarity)
        self.similarity_threshold: float = 0.70

        # Number of chunks selected after reranking (candidates for prompt)
        self.num_relevant_docs: int = 12

        # Number of initial retrieval candidates from Chroma before reranking
        self.retrieve_candidates: int = 24

        # MMR tradeoff: higher favors relevance, lower favors diversity
        self.mmr_lambda: float = 0.65

        # Maximum number of chunks included in the final LLM context
        self.max_context_chunks: int = 8

        # Maximum characters included in the final LLM context
        self.max_context_chars: int = 12000

        # Number of texts per embedding request to Ollama/Azure
        self.embedding_batch_size: int = 16

        # Number of vectors per add() call to Chroma
        self.chroma_add_batch_size: int = 512

        # Enable extra debug logging
        self.debug: bool = False

        # Manifest filename used to track ingested files
        self.manifest_filename: str = ".rag_manifest.json"

    def init_parameters(self, parameters: Dict[str, Any]) -> None:
        """Apply parameters from a dict and initialize models and database clients."""
        for key, value in parameters.items():
            setattr(self, key, value)
        self.initialize_model()

    def calculate(self) -> str:
        """Compatibility method for the parent framework."""
        return "Output calculated"

    def initialize_model(self) -> None:
        """Create LLM/embedding clients and open the Chroma collection."""
        self.ollama_client = self._build_ollama_client()

        self.chroma_client = self._build_chroma_client()

        if not self.collection_name:
            raise ValueError("collection_name must be set")

        self.chroma_collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        logger.info(
            "ChatPopup initialized. chromadb_use_http=%s, collection=%s",
            self.chromadb_use_http,
            self.collection_name,
        )

    def _build_ollama_client(self):
        """Create an Ollama client."""
        logger.info("Using Ollama at http://%s:%s", self.ollama_host, self.ollama_port)
        return Client(host=f"http://{self.ollama_host}:{self.ollama_port}")

    def _build_chroma_client(self):
        """Create a Chroma client using HTTP or local persistence."""
        if self.chromadb_use_http:
            if not self.chromadb_host or not self.chromadb_port:
                raise ValueError(
                    "chromadb_host and chromadb_port must be set when chromadb_use_http=True"
                )
            return chromadb.HttpClient(host=self.chromadb_host, port=self.chromadb_port)

        if not self.chroma_dir:
            raise ValueError("chroma_dir must be set when chromadb_use_http=False")
        return chromadb.PersistentClient(path=self.chroma_dir)

    def delete_collection(self) -> None:
        """Delete the current Chroma collection."""
        if not self.collection_name:
            raise ValueError("collection_name must be set")
        self.chroma_client.delete_collection(name=self.collection_name)

    def manifest_path(self) -> str:
        """Return the absolute path to the ingestion manifest file."""
        if not self.docs_dir:
            raise ValueError("docs_dir must be set")
        return os.path.join(self.docs_dir, self.manifest_filename)

    def load_manifest(self) -> Dict[str, Any]:
        """Load the manifest containing file signatures for incremental ingestion."""
        path = self.manifest_path()
        if not os.path.exists(path):
            return {"files": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "files" not in data or not isinstance(data["files"], dict):
                return {"files": {}}
            return data
        except Exception:
            logger.exception("Failed to read manifest; starting fresh.")
            return {"files": {}}

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        """Write manifest to disk atomically."""
        path = self.manifest_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def file_signature(self, file_path: str) -> Dict[str, Any]:
        """Return a lightweight signature used to detect file changes."""
        st = os.stat(file_path)
        return {"mtime": int(st.st_mtime), "size": int(st.st_size)}

    def chunksplitter_for_embeddings(
        self, text: str, max_words: int, overlap_words: int = 0
    ) -> List[str]:
        """Split text into overlapping word chunks suitable for embedding models."""
        if max_words <= 0:
            return []
        if overlap_words < 0:
            raise ValueError("overlap_words must be >= 0")
        if overlap_words >= max_words:
            raise ValueError("overlap_words must be smaller than max_words")

        words = re.findall(r"\S+", text)
        if not words:
            return []

        step = max_words - overlap_words
        chunks: List[str] = []

        for start in range(0, len(words), step):
            chunk_words = words[start : start + max_words]
            if not chunk_words:
                break
            chunks.append(" ".join(chunk_words))
            if start + max_words >= len(words):
                break

        return chunks

    def load_pdf_pages(self, file_path: str) -> List[Tuple[int, str]]:
        """Load a PDF and return a list of (page_index, page_text)."""
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        return [(int(doc.metadata.get("page", 0)), doc.page_content or "") for doc in documents]

    def load_txt(self, file_path: str) -> str:
        """Load a UTF-8 text file."""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_embedding(self, user_message: str) -> List[float]:
        """Embed a user query string for retrieval."""
        response = self.ollama_client.embeddings(
            model=self.ollama_embeddings_model, prompt=user_message
        )
        return response["embedding"]

    def is_context_error(self, e: Exception) -> bool:
        """Return True if an exception indicates an embedding context-length overflow."""
        msg = str(e).lower()
        return ("exceeds the context length" in msg) or ("context length" in msg)

    def embed_one_ollama(self, text: str) -> List[float]:
        """Embed one text, shrinking it iteratively if Ollama rejects it as too long."""
        text = (text or "").strip()
        if not text:
            return []

        words = re.findall(r"\S+", text)
        if not words:
            return []

        min_words = 24
        max_attempts = 8
        n = len(words)

        for _ in range(max_attempts):
            attempt_text = " ".join(words[:n])
            try:
                resp = self.ollama_client.embed(
                    model=self.ollama_embeddings_model, input=[attempt_text]
                )
                return resp.get("embeddings", [[]])[0]
            except Exception as e:
                if not self.is_context_error(e):
                    raise
                n = max(min_words, n // 2)
                if n <= min_words:
                    try:
                        resp = self.ollama_client.embed(
                            model=self.ollama_embeddings_model,
                            input=[" ".join(words[:min_words])],
                        )
                        return resp.get("embeddings", [[]])[0]
                    except Exception as e2:
                        if self.is_context_error(e2):
                            return []
                        raise
        return []

    def safe_ollama_embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch; if the batch fails, embed items individually with shrink-on-failure."""
        try:
            resp = self.ollama_client.embed(model=self.ollama_embeddings_model, input=texts)
            embeds = resp.get("embeddings", [])
            if len(embeds) != len(texts):
                raise RuntimeError(
                    f"Ollama returned {len(embeds)} embeddings for {len(texts)} inputs."
                )
            return embeds
        except Exception as e:
            if not self.is_context_error(e):
                raise
            return [self.embed_one_ollama(t) for t in texts]

    def get_embedding_list(self, chunks: List[str]) -> List[List[float]]:
        """Embed a list of chunks using batching."""
        embeddings: List[List[float]] = []
        bs = max(1, int(self.embedding_batch_size))
        for i in range(0, len(chunks), bs):
            embeddings.extend(self.safe_ollama_embed_batch(chunks[i : i + bs]))
        return embeddings

    def detect_language(self, text: str) -> str:
        """Detect language of a text sample. Returns 'en', 'nl' etc. ."""
        sample = (text or "").strip()
        if not sample:
            return "unknown"

        sample = re.sub(r"\s+", " ", sample)[:2500]

        lang, score = langid.classify(sample)
        return lang if lang else "unknown"

    def translate_to_english(self, text: str) -> str:
        """Translate text to English while preserving numbers and table-like structure."""
        if not (text or "").strip():
            return ""

        # Translate in chunks to avoid context limits
        max_words = int(getattr(self, "translation_chunk_size", self.chunk_size))
        overlap = int(getattr(self, "translation_chunk_overlap", self.chunk_overlap))

        chunks = self.chunksplitter_for_embeddings(text, max_words=max_words, overlap_words=overlap)
        out_chunks: List[str] = []

        for ch in chunks:
            prompt = (
                "You are a translation engine.\n"
                "Translate the following text FROM DUTCH TO ENGLISH.\n\n"
                "Rules:\n"
                "- Output ONLY the translated English text.\n"
                "- Do NOT add explanations, comments, or prefixes.\n"
                "- Do NOT repeat the instructions.\n"
                "- Preserve all numbers, units, names, and addresses exactly.\n"
                "- Preserve line breaks and table-like formatting.\n"
                "- If a word is already English or a proper name, keep it unchanged.\n\n"
                "DUTCH TEXT:\n"
                f"{ch}\n\n"
                "ENGLISH:"
            )

            translated = (
                self.ollama_client.generate(
                    model=self.ollama_translation_llm,
                    prompt=prompt,
                    stream=False,
                    options={
                        "temperature": 0,
                        "top_p": 0.1,
                        "num_predict": 2048,
                        "stop": [
                            "Here is",
                            "Here’s",
                            "Translation:",
                            "Translated text:",
                            "Note:",
                        ],
                    },
                )
                .model_dump()
                .get("response", "")
            )
            out_chunks.append(translated.strip())
        return "\n\n".join(out_chunks).strip()

    def maybe_translate_text(self, text: str) -> tuple[str, str, bool]:
        """Detect language and translate to English if needed."""
        lang = self.detect_language(text)

        # If Dutch, translate. You can extend this to translate any non-English.
        if lang == "nl":
            translated = self.translate_to_english(text)
            return translated, lang, True

        return text, lang, False

    def update_data(self) -> None:
        """Ingest new/changed files into Chroma and delete removed files using a local manifest."""
        if not self.docs_dir:
            raise ValueError("docs_dir must be set")
        if not os.path.exists(self.docs_dir):
            logger.warning("No directory found: %s", self.docs_dir)
            return

        tic_total = time.time()
        manifest = self.load_manifest()
        known_files: Dict[str, Dict[str, Any]] = manifest.get("files", {})

        all_files = [
            f
            for f in os.listdir(self.docs_dir)
            if os.path.isfile(os.path.join(self.docs_dir, f))
            and (f.lower().endswith(".pdf") or f.lower().endswith(".txt"))
        ]

        new_or_changed: List[str] = []
        current_signatures: Dict[str, Dict[str, Any]] = {}
        for fn in all_files:
            fp = os.path.join(self.docs_dir, fn)
            sig = self.file_signature(fp)
            current_signatures[fn] = sig
            if fn not in known_files or known_files[fn] != sig:
                new_or_changed.append(fn)

        deleted_files = [fn for fn in known_files.keys() if fn not in current_signatures]

        logger.info(
            "Ingestion scan: %d total files, %d new/changed, %d deleted",
            len(all_files),
            len(new_or_changed),
            len(deleted_files),
        )

        for missing in deleted_files:
            try:
                self.chroma_collection.delete(where={"source": missing})
                logger.info("Deleted vectors for missing file: %s", missing)
            except Exception:
                logger.exception("Failed to delete vectors for missing file: %s", missing)
            known_files.pop(missing, None)

        if not new_or_changed:
            logger.info("No new/changed files. Done.")
            self.save_manifest({"files": known_files})
            return

        chunk_records: List[ChunkRecord] = []
        for fn in new_or_changed:
            fp = os.path.join(self.docs_dir, fn)

            try:
                self.chroma_collection.delete(where={"source": fn})
            except Exception:
                logger.exception("Failed to delete old vectors for changed file: %s", fn)

            try:
                if fn.lower().endswith(".txt"):
                    text = self.load_txt(fp)
                    chunk_records.extend(
                        self.chunk_text_with_metadata(fn, 0, text, current_signatures[fn])
                    )
                else:
                    for page_num, page_text in self.load_pdf_pages(fp):
                        processed_text, lang, translated = self.maybe_translate_text(page_text)

                        chunk_records.extend(
                            self.chunk_text_with_metadata(
                                fn,
                                page_num,
                                processed_text,
                                current_signatures[fn],
                                lang=lang,
                                translated=translated,
                            )
                        )

                known_files[fn] = current_signatures[fn]
                logger.info("Prepared chunks for %s", fn)
            except Exception:
                logger.exception("Failed reading/chunking file: %s", fn)

        if not chunk_records:
            logger.warning("No chunks produced. Nothing to ingest.")
            self.save_manifest({"files": known_files})
            return

        logger.info(
            "Embedding %d chunks (batch=%d)...", len(chunk_records), self.embedding_batch_size
        )
        tic_embed = time.time()
        texts = [cr.text for cr in chunk_records]
        embeddings = self.get_embedding_list(texts)
        if len(embeddings) != len(chunk_records):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(embeddings)}"
                f" for {len(chunk_records)} chunks"
            )
        logger.info("Embeddings done in %.3fs", time.time() - tic_embed)

        logger.info("Adding to Chroma (batch=%d)...", self.chroma_add_batch_size)
        tic_add = time.time()
        bs_add = max(1, int(self.chroma_add_batch_size))
        for i in range(0, len(chunk_records), bs_add):
            batch_recs = chunk_records[i : i + bs_add]
            batch_emb = embeddings[i : i + bs_add]
            self.chroma_collection.add(
                ids=[r.chunk_id for r in batch_recs],
                documents=[r.text for r in batch_recs],
                embeddings=batch_emb,
                metadatas=[r.metadata for r in batch_recs],
            )
        logger.info("Chroma add done in %.3fs", time.time() - tic_add)

        self.save_manifest({"files": known_files})
        logger.info("Update complete in %.3fs", time.time() - tic_total)

    def chunk_text_with_metadata(
        self,
        source: str,
        page: int,
        text: str,
        file_sig: Dict[str, Any],
        lang: str = "unknown",
        translated: bool = False,
    ) -> List[ChunkRecord]:
        """Normalize and chunk page text, then attach metadata for citations and filtering."""
        cleaned = re.sub(r"[ \t]+", " ", text or "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

        max_words = int(getattr(self, "embedding_chunk_size", self.chunk_size or 200))
        overlap = int(getattr(self, "embedding_chunk_overlap", self.chunk_overlap or 0))
        chunks = self.chunksplitter_for_embeddings(
            cleaned, max_words=max_words, overlap_words=overlap
        )

        safe_chunks: List[str] = []
        hard_cap = max_words
        for ch in chunks:
            wc = len(re.findall(r"\S+", ch))
            if wc <= hard_cap:
                safe_chunks.append(ch)
            else:
                safe_chunks.extend(
                    self.chunksplitter_for_embeddings(ch, max_words=hard_cap, overlap_words=0)
                )

        records: List[ChunkRecord] = []
        for idx, ch in enumerate(safe_chunks):
            chunk_id = f"{source}::p{page+1}::c{idx+1}"
            meta = {
                "source": source,
                "page": int(page),
                "chunk": int(idx),
                "mtime": file_sig.get("mtime"),
                "size": file_sig.get("size"),
                "words": len(re.findall(r"\S+", ch)),
                "lang": lang,
                "translated": bool(translated),
            }
            records.append(ChunkRecord(chunk_id=chunk_id, text=ch, metadata=meta))
        return records

    @staticmethod
    def cosine_sim(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity without numpy."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = 0.0
        na = 0.0
        nb = 0.0
        for x, y in zip(a, b):
            fx = float(x)
            fy = float(y)
            dot += fx * fy
            na += fx * fx
            nb += fy * fy
        if na <= 0.0 or nb <= 0.0:
            return 0.0
        return dot / ((na**0.5) * (nb**0.5))

    def mmr_rerank(
        self,
        query_emb: List[float],
        candidates: List[Dict[str, Any]],
        top_k: int,
        lam: float,
    ) -> List[Dict[str, Any]]:
        """Select a diverse set of relevant chunks using Max Marginal Relevance (MMR)."""
        if not candidates:
            return []

        candidates = sorted(candidates, key=lambda x: x.get("sim", 0.0), reverse=True)
        selected: List[Dict[str, Any]] = []
        remaining = candidates[:]

        while remaining and len(selected) < top_k:
            if not selected:
                selected.append(remaining.pop(0))
                continue

            best_idx = 0
            best_score = -1e9
            for i, cand in enumerate(remaining):
                rel = float(cand.get("sim", 0.0))
                div = 0.0
                cand_emb = cand.get("emb", [])
                for s in selected:
                    div = max(div, self.cosine_sim(cand_emb, s.get("emb", [])))
                score = lam * rel - (1.0 - lam) * div
                if score > best_score:
                    best_score = score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected

    def filter_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and filter Chroma query results by similarity threshold."""

        def first_list(key: str) -> list:
            val = context.get(key)
            if not val or len(val) == 0:
                return []
            first = val[0]
            if first is None:
                return []
            try:
                return first.tolist()
            except AttributeError:
                return list(first) if isinstance(first, (tuple, list)) else first

        docs = first_list("documents")
        metas = first_list("metadatas")
        ids = first_list("ids")
        dists = first_list("distances")
        embs = first_list("embeddings")

        if not embs or len(embs) != len(docs):
            embs = [None] * len(docs)

        (filtered_docs, filtered_metas, filtered_ids, filtered_sims, filtered_embs) = (
            [],
            [],
            [],
            [],
            [],
        )
        for doc, meta, doc_id, dist, emb in zip(docs, metas, ids, dists, embs):
            sim = 1.0 - float(dist)
            if sim >= float(self.similarity_threshold):
                filtered_docs.append(doc)
                filtered_metas.append(meta)
                filtered_ids.append(doc_id)
                filtered_sims.append(sim)
                filtered_embs.append(emb)

        if self.debug:
            logger.debug(
                "Retrieved %d candidates, %d passed threshold %.3f",
                len(docs),
                len(filtered_docs),
                float(self.similarity_threshold),
            )

        return {
            "documents": filtered_docs,
            "metadatas": filtered_metas,
            "ids": filtered_ids,
            "similarities": filtered_sims,
            "embeddings": filtered_embs,
        }

    def get_response(self, prompt: str) -> str:
        """Generate an answer from the selected LLM."""
        response = self.ollama_client.generate(
            model=self.ollama_llm_model,
            prompt=prompt,
            stream=False,
            options={"temperature": 0, "num_ctx": 8192},
        )
        return response.model_dump().get("response", "")

    def build_prompt(
        self,
        user_message: str,
        selected: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Build RAG prompt and return structured citation items for UI display."""
        ctx_parts: List[str] = []
        citation_items: List[Dict[str, Any]] = []

        total_chars = 0
        for item in selected[: self.max_context_chunks]:
            doc = item["doc"]
            meta = item["meta"] or {}
            cid = item["id"]

            src = meta.get("source", "unknown")
            page = meta.get("page", None)
            chunk = meta.get("chunk", None)

            # This stays in-context so the LLM can cite inside the answer if it wants
            cite = f"{src} p{page} c{chunk} [{cid}]"
            snippet = doc.strip()

            add_len = len(snippet) + len(cite) + 10
            if total_chars + add_len > int(self.max_context_chars):
                break

            ctx_parts.append(f"[{cite}]\n{snippet}")

            # Structured citation info for the frontend
            citation_items.append(
                {
                    "source": str(src),
                    "page": int(page) if page is not None else None,
                    "chunk": int(chunk) if chunk is not None else None,
                    "id": str(cid),
                }
            )

            total_chars += add_len

        context_block = "\n\n".join(ctx_parts)

        prompt = (
            "You are a careful assistant. Answer the user's question"
            " using ONLY the provided context.\n"
            "If the answer is not contained in the context, reply exactly:"
            ' "I don\'t know." \n'
            "Do NOT add a bibliography or citations section.\n"
            "Be concise and factual. If the user asks for a table or list,"
            " format it clearly.\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            f"QUESTION:\n{user_message}\n\n"
            "ANSWER:"
        )

        return prompt, citation_items

    def process_prompt(self, user_message: str) -> Dict[str, Any]:
        """Answer a question by retrieving relevant chunks and generating a grounded response."""
        logger.info("Processing prompt...")

        tic = time.time()
        query_emb = self.get_embedding(user_message)
        logger.info("Query embedding computed in %.3fs", time.time() - tic)

        n_candidates = (
            int(self.retrieve_candidates)
            if self.retrieve_candidates
            else int(self.num_relevant_docs)
        )
        tic = time.time()
        context = self.chroma_collection.query(
            query_embeddings=query_emb,
            n_results=n_candidates,
            include=["documents", "metadatas", "distances", "embeddings"],
        )
        logger.info(
            "Chroma query returned in %.3fs (n_results=%d)", time.time() - tic, n_candidates
        )

        filtered = self.filter_context(context)
        docs = filtered["documents"]
        metas = filtered["metadatas"]
        ids = filtered["ids"]
        sims = filtered["similarities"]
        embs = filtered["embeddings"]

        if not docs:
            return {"answer": "I don't know.", "citations": [], "sources": []}

        candidates = [
            {"doc": d, "meta": m, "id": i, "sim": s, "emb": e}
            for d, m, i, s, e in zip(docs, metas, ids, sims, embs)
        ]

        # If Chroma didn't return embeddings, compute them for MMR reranking
        missing_idx = [idx for idx, c in enumerate(candidates) if c["emb"] is None]
        if missing_idx:
            texts_to_embed = [candidates[idx]["doc"] for idx in missing_idx]
            new_embs = self.get_embedding_list(texts_to_embed)
            for idx, e in zip(missing_idx, new_embs):
                candidates[idx]["emb"] = e if e else None  # keep None if embedding failed

        if missing_idx:
            # fallback: just take top by similarity, no MMR
            selected = sorted(candidates, key=lambda x: x["sim"], reverse=True)[
                : int(self.num_relevant_docs)
            ]
        else:
            selected = self.mmr_rerank(
                query_emb=query_emb,
                candidates=candidates,
                top_k=int(self.num_relevant_docs),
                lam=float(self.mmr_lambda),
            )

        prompt, citation_items = self.build_prompt(user_message, selected)

        tic = time.time()
        response = self.get_response(prompt)
        logger.info("Response generated in %.3fs", time.time() - tic)

        if response.strip() == "I don't know.":
            return {"answer": response, "citations": []}

        # Deduplicate citations by (source, page) while preserving order
        seen = set()
        deduped = []
        for c in citation_items:
            key = (c["source"], c["page"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)

        return {"answer": response, "citations": deduped}
