Well Schematics
===============

Description
---------------------------
Comprehensive tool for creating, visualizing, and managing detailed well 
schematics diagrams for well integrity management.

Schematics components
---------------------------
Tubulars
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Casing** — Pipe cemented in the wellbore (conductor, surface, intermediate); can be tapered. Defines top/bottom depth, OD/ID, and optional openhole.
  * **Tubing** — Production conduit inside casing; can include an ESP interval.
  * **Liner** — Casing that does not extend to surface. Same depth/OD/ID as other tubulars.

  **Options:** Type: Casing | Tubing | Liner. Casing can be tapered (two segments). Hanger seal: Single Seal Hanger | Double Seal Hanger.

Fluids
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Inner fluids** — Fluids inside a tubular. Defined by type, location, and depth interval (top–bottom).
  * **Annulus fluids** — Fluids in the ring between two tubulars; use location “Outside”.

  **Options:** Fluid type: Brine | Oil | Mud | Gas | Water | Air | N2 | Empty. Location: Inside | Outside.

Cements
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Cement** — Cement in the wellbore (inside or outside a tubular). Defined by type, location, and depth interval.

  **Options:** Cement type: Standard | Foamed | Lightweight | Ultra-Lightweight. Location: Inside | Outside.

Packers
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Packer** — Seals the annulus at a depth interval. Placed within a tubular unit.

  **Options:** Packer type: Standard | Mechanical | Retrievable | Permanent | Inflatable | Hydraulic | Compression | Tension.

Plugs
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Plug** — Blocks the bore at a depth. Placed within a tubular unit.

  **Options:** Plug type: Cement | Bridge | Mechanical.

Screens
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Screen** — Completion screen over a depth interval (e.g. for sand control). Placed within a tubular unit.

  **Options:** Screen type: Wire Wrap | Slotted | Perforated | Mesh.

General (layout and figure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Layout mode:** Uniform | Depth Transformed (Uniform: fixed width; Depth Transformed: scale by depth).
  * **Uniform Width** — Tubular Width.
  * **Uniform Spacing** — Annular Space.
  * **Figure Size Width** — Figure Width.
  * **Figure Size Height** — Figure height.

Wellhead
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Enable Wellhead Valves** — Toggle to show/hide wellhead valves on the schematic.
  * **A-Ring, B-Ring, C-Ring, D-Ring** — For each ring: Enable ring; Include Left Valves; Include Right Valves. Controls which annulus valves are drawn at the wellhead.

Xmas Tree
~~~~~~~~~~~~~~~~~~~~~~~~~~~
  * **Enable X-mas Tree** — Toggle to show/hide the Christmas tree on the schematic.
  * **Options:** Lower Master Valve | Upper Master Valve | Swab Valve | Wing Valves | Left Wing Valve | Right Wing Valve. Each can be included or excluded in the drawn tree.

Workflow (per Well Schematics app)
------------------------------------
1. **Select well** — Choose **Well Name** from the dropdown (well list is loaded from the project).
        .. image:: images/application_schematics_1.png
            :width: 100%
            :align: center
2. **Create or load a schematic**
   * **Create New** — Click **Create New**. Choose a template (Simple Well, Standard Well, Double Skin, or Create from Scratch). The form opens with template data or empty.
   * **Load existing** — Select a saved schematic from the dropdown and click **Load Selected** to load it into the form.

        .. image:: images/application_schematics_2.png
          :width: 100%
          :align: center

3. **Define units**
   * **Create New Unit** — Click **Create New Unit**. Fill the **Tubulars** tab (type, name, depths, OD/ID, optional openhole, draw shoe, hanger seal; for tubing, optional ESP). Add **Fluids**, **Cements**, **Packers**, **Plugs**, or **Screens** in their tabs. Set **General** (layout, figure size), **Wellhead**, and **Xmas Tree** if needed. Click **Save Unit**.
   * **Edit unit** — In the unit list, select a unit, then click **Edit Selected Unit**. Change fields and sub-elements as needed. Click **Save Changes** to keep, **Delete** to remove the unit, or **Cancel Edit** to discard.
          
          .. image:: images/application_schematics_3.png
            :width: 100%
            :align: center

4. **Preview** — Click **Generate Schematic** to draw the diagram in the schematic output card.

5. **Save schematic** — Enter a **Schematic Name** and click **Save Schematic** to save to the server for the selected well.

6. **Optional** — Use **Generate JSON** to view or copy the schematic JSON. Annulus and Pressure Barrier Elements are derived from tubular and fluid data and can be passed to the Well Integrity application.




      









