function load_plant() {
    var fieldID = $('#select_project').val();
    $.ajax({
        type: 'POST',
        url: '/app/chatpopup/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {

            initialize()

        }
    })
}

load_plant()

//Initialize models
function initialize() {
    console.log('DEBUG: initialize() function called');
    $.ajax({
    type: 'POST',
    url: '/app/chatpopup/initialize_rag',  // Adjust the endpoint if necessary
    contentType: 'application/json',
    success: function () {
        console.log('initialize() function executed successfully');
    },
    error: function (xhr, status, error) {
        console.error('Error calling initialize():', error);
    }
});
}



// Open the chat popup
function openForm() {
    console.log('DEBUG: openForm() called');
    document.getElementById("myForm").style.display = "block";
    document.querySelector(".open-button").style.display = "none";
}

// Close the chat popup and show the button
function closeForm() {
    console.log('DEBUG: closeForm() called');
    document.getElementById("myForm").style.display = "none";
    document.querySelector(".open-button").style.display = "block";
}


function send() {
    console.log('DEBUG: send() called');

    let message = document.getElementById("chatMessage").value;
    if (!message.trim()) {
        console.log("DEBUG: Empty message, aborting.");
        return;
    }

    // Display user's message in the chat
    console.log("DEBUG: User message =", message);
    appendMessage("You", message);
    document.getElementById("chatMessage").value = ""; // Clear input

    let inputs = { 'message': message };

    // Show "Thinking..." placeholder
    console.log("DEBUG: Displaying 'Thinking...' message");
    appendMessage("<div class='thinking'> AI", "Searching the answer, please wait...</div>");

    // Start the background task
    $.ajax({
        type: 'POST',
        url: '/app/chatpopup/send_message',
        contentType: 'application/json',
        data: JSON.stringify(inputs),
        success: function (data) {
            console.log("DEBUG: Task started successfully. Task ID =", data.task_id);
            sessionStorage.setItem("chat_taskid", data.task_id)

            Progress_rag = setInterval(function () { get_results_rag(data.task_id) }, 2000);
        },
        error: function (xhr, status, error) {
            console.error("ERROR: Failed to start task", status, error);
            alert("Failed to start task.");
            appendMessage("AI", "Sorry, something went wrong.");
        }
    });
}

function get_results_rag(task_id) {
    $.ajax({
        type: 'POST',
        url: '/app/chatpopup/get_rag_response',
        contentType: 'application/json',
        data: JSON.stringify({ task_id: task_id }),
        success: function (data) {
            task_status = data.task_status
            if (task_status == "SUCCESS") {
                console.log("DEBUG: Task completed successfully.");
                clearInterval(Progress_rag);
                sessionStorage.removeItem("chat_taskid")
                renderResponse(data.task_result);

            }
        },
        error: function (xhr) {
            clearInterval(Progress_rag)
            sessionStorage.removeItem("chat_taskid")
        }
    })

}

function pollTaskStatus(taskId) {
    console.log("DEBUG: Starting polling for task ID:", taskId);

    const interval = setInterval(() => {
        console.log("DEBUG: Polling status for task ID:", taskId);
        $.get(`/app/chatpopup/get_rag_response?taskId=${taskId}`, function (data) {
            console.log("DEBUG: Polling response:", data);

            if (data.state === 'SUCCESS') {
                console.log("DEBUG: Task completed successfully.");
                clearInterval(interval);
                console.log(data);
                renderResponse(data.answer);
            } else if (data.state === 'FAILURE') {
                console.error("ERROR: Task failed.");
                clearInterval(interval);
                appendMessage("AI", "An error occurred while processing your request.");
            } else {
                console.log("DEBUG: Task still in progress, state =", data.state);
            }
        }).fail(function (xhr, status, error) {
            console.error("ERROR: Failed to poll task status", status, error);
            clearInterval(interval);
            appendMessage("AI", "Error checking task status.");
        });
    }, 5000);
}

function removeThinkingMessage() {
    console.log("DEBUG: Removing 'Thinking...' message");
    let chatHistory = document.getElementById("chatHistory");
    let thinkingMsg = chatHistory.querySelector(".thinking");
    if (thinkingMsg) thinkingMsg.remove();
}



function renderResponse(response) {
    console.log("DEBUG: Rendering response:", response);

    const answer = response.answer || "";
    const citations = response.citations || [];

    let formattedResponse = `<div>${answer}</div>`;

    if (citations.length > 0) {
        formattedResponse += `<div style="margin-top: 8px;"><strong>Sources</strong></div>`;

        for (let i = 0; i < citations.length; i++) {
            const c = citations[i];
            const src = c.source || "unknown";
            const page = (c.page !== null && c.page !== undefined) ? `p${c.page}` : "p?";
            formattedResponse += `
                <div style="margin-top: 4px;">
                    <strong>[${i + 1}]</strong> ${c.id}
                </div>
            `;
        }
    }

    appendMessage("AI", formattedResponse);
}


// Function to append a message to the chat
function appendMessage(sender, text) {
    const chatHistory = document.getElementById("chatHistory");
    const messageDiv = document.createElement("div");

    // Add common and specific class
    messageDiv.classList.add("chat-message");
    messageDiv.classList.add(sender === "You" ? "user-message" : "ai-message");

    messageDiv.innerHTML = `<b>${sender}:</b> ${text}`;
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    sessionStorage.setItem("chat_history", chatHistory.innerHTML)
}

// Get the input field
var input = document.getElementById("chatMessage");

// Execute a function when the user presses a key on the keyboard
input.addEventListener("keypress", function(event) {
  // If the user presses the "Enter" key on the keyboard
  if (event.key === "Enter") {
    // Cancel the default action, if needed
    event.preventDefault();
    // Trigger the button element with a click
    document.getElementById("chat_submit").click();
  }
});


function load_chat_history(){
    chatHistory = document.getElementById("chatHistory")
    console.log(chatHistory.innerHTML)

    chatHistory.innerHTML = sessionStorage.getItem("chat_history")

    task_id = sessionStorage.getItem("chat_taskid")
    if (task_id != null){
        Progress_rag = setInterval(function () { get_results_rag(task_id) }, 2000);
    }
}

load_chat_history()


