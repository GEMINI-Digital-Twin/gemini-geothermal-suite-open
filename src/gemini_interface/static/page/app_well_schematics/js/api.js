// =============================================================================
// WELL INTEGRITY MONITORING SYSTEM - API
// =============================================================================
// This file handles all AJAX interactions and UI logic for the well integrity
// monitoring application, including schematic management, log processing,
// and corrosion analysis.

// =============================================================================
// GLOBAL VARIABLES
// =============================================================================
// Store data in API format: { well: {...}, tubulars: [...] }
let schematicData = {
    well: {
        name: "",
        layout: {
            mode: "uniform",
            uniform_width: 0.1,
            uniform_spacing: 0.2,
            show_axes: true
        }
    },
    tubulars: []
};
let currentUnitIndex = -1; // -1 means no unit selected
let unitFormSyncSuspended = false;
let unitFormSyncTimer = null;
let progressInterval;

// Selected sub-component when editing (for updating existing item)
let selectedSubType = null; // 'fluid' | 'cement' | 'packer' | 'plug' | 'screen'
let selectedSubIndex = -1;
let subFormSyncSuspended = false;
let subFormSyncTimer = null;

// Active schematic document context
const SCHEMATIC_NEW_OPTION = '__new_schematic__';
let schematicDoc = {
    filename: null,
    displayName: null,
    isDirty: false,
    isLoading: false,
};
let savedSchematicList = [];
let pendingNavigationAction = null;
let suppressSchematicSelectChange = false;
let suppressWellSelectChange = false;
let previousWellValue = '';
let previousSchematicValue = '';
let namePromptMode = null; // 'save' | 'save_as'

// =============================================================================
// SCHEMA NORMALIZATION HELPERS
// =============================================================================

/**
 * Resolves seal count from num_seals (preferred) or legacy hanger_seal_type.
 */
function resolveNumSeals(tubular) {
    if (tubular.num_seals === 1 || tubular.num_seals === 2) {
        return tubular.num_seals;
    }
    if (tubular.hanger_seal_type === 'single_seal_hanger') {
        return 1;
    }
    if (tubular.hanger_seal_type === 'double_seal_hanger') {
        return 2;
    }
    return 2;
}

/**
 * Writes num_seals and removes deprecated hanger_seal_type.
 */
function applyNumSealsToTubular(tubular, numSeals) {
    tubular.num_seals = numSeals === 1 ? 1 : 2;
    delete tubular.hanger_seal_type;
}

/**
 * Syncs tubular scalar fields from the tubular form into a tubular object.
 */
function syncTubularFieldsFromForm(tubular) {
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    if (tubular.has_spool === undefined) {
        tubular.has_spool = true;
    }
    applyNumSealsToTubular(tubular, parseInt($('#num_seals').val(), 10) || 2);
}

/**
 * Returns true when a unit is selected for editing.
 */
function hasActiveUnit() {
    return currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length;
}

/**
 * Copies passthrough top-level keys that have no dedicated UI editor.
 */
function applyPassthroughKeys(target, source) {
    if (source.item_colors) {
        target.item_colors = JSON.parse(JSON.stringify(source.item_colors));
    }
    if (source.patch_colors) {
        target.patch_colors = JSON.parse(JSON.stringify(source.patch_colors));
    }
}

/**
 * Normalizes loaded schematic data to the current API schema.
 */
function normalizeLoadedSchematic(data) {
    const copy = JSON.parse(JSON.stringify(data));
    if (!copy.tubulars && copy.casings) {
        copy.tubulars = copy.casings;
    }
    delete copy.casings;
    (copy.tubulars || []).forEach(t => {
        applyNumSealsToTubular(t, resolveNumSeals(t));
    });
    if (!copy.well) {
        copy.well = { name: "" };
    }
    return copy;
}

/**
 * Returns true when any legacy wellhead per-ring checkbox is enabled.
 */
function hasLegacyWellheadRingConfig() {
    return $('#wellhead_a_enabled').is(':checked') ||
        $('#wellhead_b_enabled').is(':checked') ||
        $('#wellhead_c_enabled').is(':checked') ||
        $('#wellhead_d_enabled').is(':checked');
}

/**
 * Shows or hides the legacy wellhead per-ring section.
 */
function setWellheadLegacySectionVisible(visible) {
    if (visible) {
        $('#wellhead_legacy_section').slideDown();
        $('#wellhead_legacy_toggle_icon').removeClass('fa-chevron-down').addClass('fa-chevron-up');
    } else {
        $('#wellhead_legacy_section').slideUp();
        $('#wellhead_legacy_toggle_icon').removeClass('fa-chevron-up').addClass('fa-chevron-down');
    }
}

/**
 * Builds a legacy wellhead ring config from form fields.
 */
function buildWellheadRingConfig(ringId) {
    const lower = ringId.toLowerCase();
    if (!$('#wellhead_' + lower + '_enabled').is(':checked')) {
        return null;
    }
    const ring = {
        enabled: true,
        include_left_valves: $('#wellhead_' + lower + '_left_valves').is(':checked'),
        include_right_valves: $('#wellhead_' + lower + '_right_valves').is(':checked')
    };
    return ring;
}

/**
 * Populates legacy wellhead ring form fields from data.
 */
function populateWellheadRingForm(ringId, ringData) {
    if (!ringData) {
        return;
    }
    const lower = ringId.toLowerCase();
    $('#wellhead_' + lower + '_enabled').prop('checked', ringData.enabled !== false);
    $('#wellhead_' + lower + '_left_valves').prop('checked', ringData.include_left_valves || false);
    $('#wellhead_' + lower + '_right_valves').prop('checked', ringData.include_right_valves !== false);
}

/**
 * Adds one tapered-casing segment row to the segment table.
 */
function addSegmentRow(segment) {
    const seg = segment || {};
    const rowCount = $('#segments_table_body tr').length;
    const row = $(
        '<tr>' +
        '<td><input type="number" class="form-control form-control-sm seg-top" step="0.1" value="' + (seg.top_depth != null ? seg.top_depth : '') + '"></td>' +
        '<td><input type="number" class="form-control form-control-sm seg-bottom" step="0.1" value="' + (seg.bottom_depth != null ? seg.bottom_depth : '') + '"></td>' +
        '<td><input type="number" class="form-control form-control-sm seg-id" step="0.001" value="' + (seg.inner_diameter != null ? seg.inner_diameter : '') + '"></td>' +
        '<td><input type="number" class="form-control form-control-sm seg-od" step="0.001" value="' + (seg.outer_diameter != null ? seg.outer_diameter : '') + '"></td>' +
        '<td><button type="button" class="btn btn-default btn-xs remove-segment-btn"' + (rowCount < 2 ? ' disabled' : '') + '><i class="fa fa-trash"></i></button></td>' +
        '</tr>'
    );
    $('#segments_table_body').append(row);
    updateSegmentRemoveButtons();
}

/**
 * Enables/disables segment remove buttons based on row count.
 */
function updateSegmentRemoveButtons() {
    const rows = $('#segments_table_body tr');
    rows.find('.remove-segment-btn').prop('disabled', rows.length <= 2);
}

/**
 * Populates the tapered segment table from segment data.
 */
function populateSegmentsTable(segments) {
    $('#segments_table_body').empty();
    if (segments && segments.length > 0) {
        segments.forEach(seg => addSegmentRow(seg));
    } else {
        addSegmentRow({});
        addSegmentRow({});
    }
}

/**
 * Reads tapered segment rows from the segment table.
 */
function buildSegmentsFromTable() {
    const segments = [];
    $('#segments_table_body tr').each(function() {
        const topDepth = parseFloat($(this).find('.seg-top').val());
        const bottomDepth = parseFloat($(this).find('.seg-bottom').val());
        const innerDiameter = parseFloat($(this).find('.seg-id').val());
        const outerDiameter = parseFloat($(this).find('.seg-od').val());
        if (isNaN(topDepth) || isNaN(bottomDepth) || isNaN(innerDiameter) || isNaN(outerDiameter)) {
            return;
        }
        segments.push({
            top_depth: topDepth,
            bottom_depth: bottomDepth,
            inner_diameter: innerDiameter,
            outer_diameter: outerDiameter
        });
    });
    return segments;
}

/**
 * Initializes default tapered segments from unit top/bottom and diameters.
 */
function initDefaultSegmentsFromUnitFields() {
    const topDepth = parseFloat($('#unit_top').val()) || 0;
    const bottomDepth = parseFloat($('#unit_bottom').val()) || 1000;
    const topID = parseFloat($('#unit_id').val()) || 9.0;
    const topOD = parseFloat($('#unit_od').val()) || 9.625;
    const midDepth = topDepth + (bottomDepth - topDepth) * 0.5;
    populateSegmentsTable([
        {
            top_depth: topDepth,
            bottom_depth: midDepth,
            inner_diameter: topID,
            outer_diameter: topOD
        },
        {
            top_depth: midDepth,
            bottom_depth: bottomDepth,
            inner_diameter: topID - 0.5,
            outer_diameter: topOD - 0.5
        }
    ]);
}

/**
 * Applies optional fluid density from form fields.
 */
function applyOptionalFluidFields(fluid) {
    const density = parseFloat($('#fluid_density').val());
    if (!isNaN(density)) {
        fluid.density = density;
    } else {
        delete fluid.density;
    }
}

/**
 * Preserves color fields from previous well config when saving from form.
 */
function preserveWellColorFields(prevWell, nextWell) {
    if (prevWell.caprock && prevWell.caprock.color && nextWell.caprock) {
        nextWell.caprock.color = prevWell.caprock.color;
    }
    if (prevWell.xmas_tree && nextWell.xmas_tree) {
        [
            'lower_master_valve_color',
            'upper_master_valve_color',
            'left_wing_valve_color',
            'right_wing_valve_color',
            'swab_valve_color'
        ].forEach(key => {
            if (prevWell.xmas_tree[key]) {
                nextWell.xmas_tree[key] = prevWell.xmas_tree[key];
            }
        });
    }
    if (prevWell.wellhead_valves && nextWell.wellhead_valves) {
        ['A', 'B', 'C', 'D'].forEach(ringId => {
            const prevRing = prevWell.wellhead_valves[ringId];
            const nextRing = nextWell.wellhead_valves[ringId];
            if (!prevRing || !nextRing) {
                return;
            }
            if (prevRing.left_valve_color) {
                nextRing.left_valve_color = prevRing.left_valve_color;
            }
            if (prevRing.right_valve_color) {
                nextRing.right_valve_color = prevRing.right_valve_color;
            }
        });
    }
}

/**
 * Syncs well-level config from form into schematicData.
 */
function syncWellConfigFromForm() {
    const prevWell = JSON.parse(JSON.stringify(schematicData.well || {}));
    schematicData.well.layout = buildLayoutConfig();
    schematicData.well.wellhead_valves = buildWellheadValvesConfig();
    schematicData.well.xmas_tree = buildXmasTreeConfig();
    preserveWellColorFields(prevWell, schematicData.well);
    const caprock = buildCaprockConfig();
    if (caprock) {
        schematicData.well.caprock = caprock;
    } else {
        delete schematicData.well.caprock;
    }
}

/**
 * Populates all well-level form sections from schematic data.
 */
function populateWellConfigForms(data) {
    schematicDoc.isLoading = true;
    const well = data.well || {};
    if (well.layout) {
        populateLayoutForm(well.layout);
    }
    if (well.wellhead_valves) {
        populateWellheadValvesForm(well.wellhead_valves);
    } else {
        resetWellheadFormDefaults();
    }
    if (well.xmas_tree) {
        populateXmasTreeForm(well.xmas_tree);
    }
    if (well.caprock) {
        populateCaprockForm(well.caprock);
    } else {
        resetCaprockForm();
    }
    schematicDoc.isLoading = false;
    updateSchematicToolbar();
}

// =============================================================================
// TEMPLATE DEFINITIONS
// =============================================================================

/**
 * Returns template 1: Simple Well (Conductor + Surface Casing + Tubing)
 */
function getSimpleWellTemplate(wellName) {
    return {
        well: {
            name: wellName || "Well",
            layout: {
                mode: "uniform",
                uniform_width: 0.1,
                uniform_spacing: 0.2,
                show_axes: true
            },
            xmas_tree: {
                enabled: true,
                include_lower_master: false,
                include_upper_master: true,
                include_swab: true,
                include_wings: true,
                include_left_wing: true,
                include_right_wing: false
            },
            wellhead_valves: {
                enabled: true,
                show_seals: true
            },
            esp: {
                enabled: false
            }
        },
        tubulars: [
            {
                name: "Conductor",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 60,
                inner_diameter: 12.615,
                outer_diameter: 13.375,
                openhole_diameter: 14.0,
                hole_top_depth: 0,
                hole_bottom_depth: 60,
                draw_shoe: true,
                has_spool: true,
                num_seals: 1,
                cements: [
                    {
                        cement_type: "standard",
                        top_depth: 0,
                        bottom_depth: 60,
                        location: "outside"
                    }
                ]
            },
            {
                name: "Surface Casing",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 300,
                inner_diameter: 8.5,
                outer_diameter: 9.625,
                openhole_diameter: 12.25,
                hole_top_depth: 60,
                hole_bottom_depth: 300,
                draw_shoe: true,
                has_spool: true,
                num_seals: 2
            },
            {
                name: "Production Tubing",
                tubular_type: "tubing",
                top_depth: 0,
                bottom_depth: 1000,
                inner_diameter: 3.958,
                outer_diameter: 4.5,
                draw_shoe: false,
                num_seals: 1,
                fluids: [
                    {
                        fluid_type: "oil",
                        top_depth: 0,
                        bottom_depth: 1000,
                        location: "inside"
                    }
                ]
            }
        ]
    };
}

/**
 * Returns template 2: Standard Well (Multiple Casings + Tubing)
 */
function getStandardWellTemplate(wellName) {
    return {
        well: {
            name: wellName || "Well",
            layout: {
                mode: "uniform",
                uniform_width: 0.1,
                uniform_spacing: 0.2,
                show_axes: true
            }
        },
        tubulars: [
            {
                name: "Conductor",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 60,
                inner_diameter: 12.615,
                outer_diameter: 13.375,
                openhole_diameter: 13.375,
                hole_top_depth: 0,
                hole_bottom_depth: 60,
                draw_shoe: true,
                num_seals: 1
            },
            {
                name: "Surface Casing",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 300,
                inner_diameter: 8.5,
                outer_diameter: 9.625,
                openhole_diameter: 12.25,
                hole_top_depth: 60,
                hole_bottom_depth: 300,
                draw_shoe: true,
                num_seals: 2,
                cements: [
                    {
                        cement_type: "standard",
                        top_depth: 0,
                        bottom_depth: 250,
                        location: "outside"
                    }
                ]
            },
            {
                name: "Intermediate Casing",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 800,
                inner_diameter: 6.094,
                outer_diameter: 7.0,
                openhole_diameter: 8.5,
                hole_top_depth: 300,
                hole_bottom_depth: 800,
                draw_shoe: true,
                num_seals: 2,
                cements: [
                    {
                        cement_type: "standard",
                        top_depth: 300,
                        bottom_depth: 750,
                        location: "outside"
                    }
                ]
            },
            {
                name: "Production Tubing",
                tubular_type: "tubing",
                top_depth: 0,
                bottom_depth: 1200,
                inner_diameter: 3.958,
                outer_diameter: 4.5,
                draw_shoe: false,
                num_seals: 1,
                fluids: [
                    {
                        fluid_type: "oil",
                        top_depth: 0,
                        bottom_depth: 1200,
                        location: "inside"
                    }
                ]
            }
        ]
    };
}

/**
 * Returns template 3: Double Skin Template
 */
function getDoubleSkinTemplate(wellName) {
    return {
        well: {
            name: wellName || "Well",
            description: "Basic example with conductor and surface casing",
            layout: {
                mode: "depth_transformed",
                uniform_width: 0.05,
                uniform_spacing: 0.1,
                figure_size: [6, 10],
                show_axes: true
            },
            xmas_tree: {
                enabled: true,
                include_lower_master: true,
                include_upper_master: true,
                include_swab: true,
                include_wings: true,
                include_left_wing: true,
                include_right_wing: true,
                lower_master_valve_color: "white",
                upper_master_valve_color: "white",
                left_wing_valve_color: "white",
                right_wing_valve_color: "white",
                swab_valve_color: "white"
            },
            wellhead_valves: {
                enabled: true,
                show_seals: true,
                A: {
                    enabled: true,
                    include_left_valves: false,
                    include_right_valves: true,
                    left_valve_color: "white",
                    right_valve_color: "white"
                },
                B: {
                    enabled: true,
                    include_left_valves: true,
                    include_right_valves: false,
                    left_valve_color: "white",
                    right_valve_color: "white"
                },
                C: {
                    enabled: true,
                    include_left_valves: true,
                    include_right_valves: true,
                    left_valve_color: "white",
                    right_valve_color: "white"
                },
                D: {
                    enabled: true,
                    include_left_valves: false,
                    include_right_valves: false,
                    left_valve_color: "white",
                    right_valve_color: "white"
                }
            },
            esp: {
                enabled: false
            }
        },
        tubulars: [
            {
                name: "Conductor",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 60,
                inner_diameter: 12.615,
                outer_diameter: 13.375,
                openhole_diameter: 13.375,
                hole_top_depth: 0,
                hole_bottom_depth: 60,
                draw_shoe: true,
                num_seals: 1
            },
            {
                name: "Surface Casing",
                tubular_type: "casing",
                top_depth: 0,
                bottom_depth: 600,
                inner_diameter: 8.5,
                outer_diameter: 9.625,
                openhole_diameter: 12.25,
                hole_top_depth: 60,
                hole_bottom_depth: 600,
                draw_shoe: true,
                num_seals: 2,
                cements: [
                    {
                        cement_type: "standard",
                        top_depth: 20,
                        bottom_depth: 600,
                        location: "outside"
                    }
                ]
            },
            {
                name: "Intermediate Liner",
                tubular_type: "liner",
                top_depth: 500,
                bottom_depth: 1000,
                inner_diameter: 7.0,
                outer_diameter: 8.5,
                openhole_diameter: 11.0,
                hole_top_depth: 600,
                hole_bottom_depth: 1000,
                draw_shoe: true,
                num_seals: 2,
                packers: [
                    {
                        packer_type: "primary",
                        top_depth: 500,
                        bottom_depth: 550
                    }
                ],
                cements: [
                    {
                        cement_type: "standard",
                        top_depth: 600,
                        bottom_depth: 1000,
                        location: "outside"
                    }
                ]
            },
            {
                name: "Tapered Tie-Back",
                tubular_type: "tapered_casing",
                segments: [
                    {
                        top_depth: 0,
                        bottom_depth: 400,
                        inner_diameter: 6,
                        outer_diameter: 7
                    },
                    {
                        top_depth: 400,
                        bottom_depth: 1500,
                        inner_diameter: 4,
                        outer_diameter: 5
                    }
                ],
                openhole_diameter: 12.25,
                draw_shoe: true,
                num_seals: 2,
                screens: [
                    {
                        screen_type: "wire_wrap",
                        top_depth: 1000,
                        bottom_depth: 1450
                    }
                ],
                packers: [
                    {
                        packer_type: "standard",
                        top_depth: 800,
                        bottom_depth: 850
                    }
                ],
                fluids: [
                    {
                        fluid_type: "water",
                        top_depth: 200,
                        bottom_depth: 1500,
                        location: "inside"
                    },
                    {
                        fluid_type: "brine",
                        top_depth: 200,
                        bottom_depth: 800,
                        location: "outside"
                    }
                ]
            },
            {
                name: "Production Tubing",
                tubular_type: "tubing",
                top_depth: 0,
                bottom_depth: 350,
                inner_diameter: 3.958,
                outer_diameter: 4.5,
                draw_shoe: false,
                num_seals: 1,
                esp: {
                    enabled: true,
                    top_depth: 300,
                    bottom_depth: 350
                },
                fluids: [
                    {
                        fluid_type: "water",
                        top_depth: 200,
                        bottom_depth: 350,
                        location: "inside"
                    }
                ]
            }
        ]
    };
}

// =============================================================================
// INITIALIZATION
// =============================================================================
load_plant();
disableFormFields()
// =============================================================================
// PLANT & WELL MANAGEMENT
// =============================================================================

/**
 * Loads plant data and initializes well list
 */
function load_plant() {
    const fieldID = $('#select_project').val();
    
    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/load_plant',
        contentType: 'application/json',
        data: JSON.stringify({ field_name: fieldID }),
        success: function (data) {
            get_well_list();
        }
    });
}

/**
 * Fetches and populates well list dropdown
 */
function get_well_list() {
    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/get_well_list',
        contentType: 'application/json',
        data: JSON.stringify(),
        success: function (data) {
            const select = document.getElementById('select_well');
            select.options.length = 0;
            select.options.add(new Option('Select a well...', ''));

            data.forEach(well => {
                select.options.add(new Option(well, well));
            });

            $('#schematic_toolbar').show();
            updateSchematicToolbar();
        }
    });
}

// =============================================================================
// SCHEMATIC MANAGEMENT
// =============================================================================

/**
 * Resets the active schematic document metadata.
 */
function resetSchematicDoc() {
    schematicDoc.filename = null;
    schematicDoc.displayName = null;
    schematicDoc.isDirty = false;
    schematicDoc.isLoading = false;
    updateSchematicToolbar();
}

/**
 * Marks the active schematic as a new unsaved document.
 */
function setSchematicDocAsNew(displayName) {
    schematicDoc.filename = null;
    schematicDoc.displayName = displayName || 'Untitled schematic';
    schematicDoc.isDirty = true;
    schematicDoc.isLoading = false;
    updateSchematicToolbar();
}

/**
 * Sets active schematic metadata from a saved file.
 */
function setSchematicDocFromFile(filename, displayName) {
    schematicDoc.filename = filename;
    schematicDoc.displayName = displayName || filename.replace(/\.json$/i, '');
    schematicDoc.isDirty = false;
    schematicDoc.isLoading = false;
    updateSchematicToolbar();
}

/**
 * Marks schematic dirty or clean and refreshes toolbar state.
 */
function setSchematicDirty(isDirty) {
    if (schematicDoc.isLoading) {
        return;
    }
    schematicDoc.isDirty = !!isDirty;
    updateSchematicToolbar();
}

/**
 * Clears the dirty flag after save or load.
 */
function clearSchematicDirty() {
    schematicDoc.isDirty = false;
    updateSchematicToolbar();
}

/**
 * Sanitizes a schematic name for use as a filename stem.
 */
function sanitizeSchematicName(name) {
    if (!name || !String(name).trim()) {
        return '';
    }
    return String(name).trim()
        .replace(/[\\/:*?"<>|]/g, '_')
        .replace(/\.\./g, '_');
}

/**
 * Updates toolbar badges, button states, and unit count.
 */
function updateSchematicToolbar() {
    const wellSelected = !!$('#select_well').val();
    const editorOpen = $('#well_schematics_input_card').is(':visible');
    const $badge = $('#schematic_status_badge');

    $('#new_schematic_btn').prop('disabled', !wellSelected);
    $('#save_schematic_btn').prop('disabled', !wellSelected || !editorOpen);
    $('#save_as_schematic_btn').prop('disabled', !wellSelected || !editorOpen);
    $('#delete_schematic_btn').prop(
        'disabled',
        !wellSelected || !schematicDoc.filename || schematicDoc.isLoading
    );

    if (schematicDoc.isLoading) {
        $badge.removeClass('badge-saved badge-unsaved badge-idle').addClass('badge-loading');
        $badge.text('Loading…');
    } else if (!editorOpen) {
        $badge.removeClass('badge-saved badge-unsaved badge-loading').addClass('badge-idle');
        $badge.text(wellSelected ? 'No schematic open' : 'Select a well');
    } else if (schematicDoc.isDirty) {
        $badge.removeClass('badge-saved badge-idle badge-loading').addClass('badge-unsaved');
        $badge.text('Unsaved changes');
    } else if (schematicDoc.filename) {
        $badge.removeClass('badge-unsaved badge-idle badge-loading').addClass('badge-saved');
        $badge.text('Saved');
    } else {
        $badge.removeClass('badge-saved badge-loading').addClass('badge-unsaved');
        $badge.text('New schematic');
    }
}

/**
 * Populates the schematic dropdown from the saved list.
 */
function populateSchematicDropdown(selectFilename) {
    const $select = $('#saved_schematics_select');
    const currentValue = selectFilename !== undefined ? selectFilename : $select.val();

    suppressSchematicSelectChange = true;
    $select.empty();
    $select.append('<option value="">Select a schematic...</option>');
    $select.append(`<option value="${SCHEMATIC_NEW_OPTION}">(New schematic…)</option>`);

    savedSchematicList.forEach(schematic => {
        const label = schematic.modified_at
            ? `${schematic.name}`
            : schematic.name;
        $select.append(`<option value="${schematic.filename}">${label}</option>`);
    });

    if (currentValue && $select.find(`option[value="${currentValue}"]`).length) {
        $select.val(currentValue);
    } else if (schematicDoc.filename && $select.find(`option[value="${schematicDoc.filename}"]`).length) {
        $select.val(schematicDoc.filename);
    } else {
        $select.val('');
    }

    previousSchematicValue = $select.val() || '';
    suppressSchematicSelectChange = false;
}

/**
 * Checks whether a schematic filename already exists for the current well.
 */
function schematicFilenameExists(filename) {
    return savedSchematicList.some(item => item.filename === filename);
}

/**
 * Runs a callback after handling unsaved changes, if any.
 */
function confirmUnsavedIfNeeded(onProceed, onCancel) {
    if (!schematicDoc.isDirty) {
        onProceed();
        return;
    }
    pendingNavigationAction = { onProceed: onProceed, onCancel: onCancel || null };
    $('#unsaved_changes_modal').show();
}

/**
 * Closes the unsaved-changes modal and optionally runs cancel callback.
 */
function closeUnsavedChangesModal(runCancel) {
    $('#unsaved_changes_modal').hide();
    if (runCancel && pendingNavigationAction && pendingNavigationAction.onCancel) {
        pendingNavigationAction.onCancel();
    }
    pendingNavigationAction = null;
}

/**
 * Checks for saved schematics when well selection changes.
 */
function checkForSavedSchematics(selectFilename, onComplete) {
    const well_name = $('#select_well').val();

    if (!well_name) {
        hideEditorCards();
        savedSchematicList = [];
        populateSchematicDropdown('');
        updateSchematicToolbar();
        if (onComplete) {
            onComplete();
        }
        return;
    }

    $('#schematic_toolbar').show();

    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/get_saved_schematics',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function (data) {
            savedSchematicList = Array.isArray(data) ? data : [];
            populateSchematicDropdown(selectFilename);
            updateSchematicToolbar();
            if (onComplete) {
                onComplete();
            }
        },
        error: function (xhr) {
            console.error('Error loading saved schematics:', xhr);
            savedSchematicList = [];
            populateSchematicDropdown('');
            updateSchematicToolbar();
            if (onComplete) {
                onComplete();
            }
        }
    });
}

/**
 * Handles well dropdown changes with unsaved-change protection.
 */
function onWellSelectChange() {
    const $select = $('#select_well');
    const newWell = $select.val();

    if (suppressWellSelectChange) {
        suppressWellSelectChange = false;
        previousWellValue = newWell || '';
        return;
    }

    const proceed = function () {
        previousWellValue = newWell || '';
        resetSchematicDoc();
        resetAllData();
        resetUI();
        hideEditorCards();
        checkForSavedSchematics('');
    };

    if (schematicDoc.isDirty) {
        const revertWell = previousWellValue;
        confirmUnsavedIfNeeded(proceed, function () {
            suppressWellSelectChange = true;
            $select.val(revertWell);
        });
        return;
    }

    proceed();
}

/**
 * Handles schematic dropdown changes with auto-load.
 */
function onSchematicSelectChange() {
    if (suppressSchematicSelectChange) {
        return;
    }

    const schematic_filename = $('#saved_schematics_select').val();

    if (!schematic_filename) {
        previousSchematicValue = '';
        return;
    }

    if (schematic_filename === SCHEMATIC_NEW_OPTION) {
        const revertValue = previousSchematicValue;
        const openNew = function () {
            previousSchematicValue = SCHEMATIC_NEW_OPTION;
            showTemplateSelection();
        };
        if (schematicDoc.isDirty) {
            confirmUnsavedIfNeeded(openNew, function () {
                suppressSchematicSelectChange = true;
                $('#saved_schematics_select').val(revertValue);
                previousSchematicValue = revertValue;
                suppressSchematicSelectChange = false;
            });
            return;
        }
        openNew();
        return;
    }

    const revertValue = previousSchematicValue;
    const loadSelected = function () {
        previousSchematicValue = schematic_filename;
        loadSchematicByFilename(schematic_filename);
    };

    if (schematicDoc.isDirty) {
        confirmUnsavedIfNeeded(loadSelected, function () {
            suppressSchematicSelectChange = true;
            $('#saved_schematics_select').val(revertValue);
            previousSchematicValue = revertValue;
            suppressSchematicSelectChange = false;
        });
        return;
    }

    loadSelected();
}

/**
 * Loads a schematic file and populates the editor.
 */
function loadSchematicByFilename(schematic_filename) {
    const well_name = $('#select_well').val();

    if (!well_name || !schematic_filename) {
        showErrorMessage('Please select a well and a schematic');
        return;
    }

    schematicDoc.isLoading = true;
    updateSchematicToolbar();

    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/load_schematic',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function (data) {
            const wellName = $('#select_well').val() || data.well?.name || 'Well';
            let loadedData;

            if (data.well && (data.tubulars || data.casings)) {
                loadedData = data;
            } else if (data.units) {
                loadedData = {
                    well: {
                        name: wellName,
                        layout: data.well?.layout || {
                            mode: "uniform",
                            uniform_width: 0.1,
                            uniform_spacing: 0.2,
                            show_axes: true
                        },
                        wellhead_valves: data.well?.wellhead_valves,
                        xmas_tree: data.well?.xmas_tree
                    },
                    tubulars: convertOldFormatToApiFormat(data.units, wellName)
                };
            } else {
                loadedData = {
                    well: {
                        name: wellName,
                        layout: {
                            mode: "uniform",
                            uniform_width: 0.1,
                            uniform_spacing: 0.2,
                            show_axes: true
                        }
                    },
                    tubulars: []
                };
            }

            schematicData = normalizeLoadedSchematic(loadedData);
            schematicData.well.name = wellName;
            populateWellConfigForms(schematicData);

            const displayName = $('#saved_schematics_select option:selected').text();
            setSchematicDocFromFile(schematic_filename, displayName);
            suppressSchematicSelectChange = true;
            $('#saved_schematics_select').val(schematic_filename);
            previousSchematicValue = schematic_filename;
            suppressSchematicSelectChange = false;

            populateFormFromUnits();
            showSchematicUI();

            if (schematicData.tubulars.length > 0) {
                showSuccessMessage('Schematic loaded successfully!');
            } else {
                showSuccessMessage('Schematic loaded but no units found. You can add new units.');
            }
        },
        error: function (xhr) {
            schematicDoc.isLoading = false;
            updateSchematicToolbar();
            const errorMsg = xhr.responseJSON?.error ?
                `Error loading schematic: ${xhr.responseJSON.error}` :
                'Error loading schematic';
            showErrorMessage(errorMsg);
        }
    });
}

/**
 * Shows template selection modal.
 */
function showTemplateSelection() {
    if (!$('#select_well').val()) {
        showErrorMessage('Please select a well first');
        return;
    }

    $('#template_selection_modal').show();
    $('.template-card').removeClass('selected');
}

/**
 * Initializes editor state after creating a new schematic.
 */
function initializeNewSchematicEditor(displayName) {
    setSchematicDocAsNew(displayName);
    suppressSchematicSelectChange = true;
    $('#saved_schematics_select').val('');
    previousSchematicValue = '';
    suppressSchematicSelectChange = false;
    updateSchematicToolbar();
}

/**
 * Loads a template and initializes the schematic.
 */
function loadTemplate(templateType) {
    const wellName = $('#select_well').val() || 'Well';

    let template;
    switch (templateType) {
        case 'simple':
            template = getSimpleWellTemplate(wellName);
            break;
        case 'standard':
            template = getStandardWellTemplate(wellName);
            break;
        case 'double_skin':
            template = getDoubleSkinTemplate(wellName);
            break;
        default:
            showErrorMessage('Invalid template type');
            return;
    }

    schematicData = JSON.parse(JSON.stringify(template));
    schematicData.well.name = wellName;

    $('#template_selection_modal').hide();
    resetUI();
    populateFormFromUnits();
    populateWellConfigForms(schematicData);
    initializeNewSchematicEditor(`New ${templateType.replace('_', ' ')}`);
    showSchematicUI();
    showSuccessMessage(`Template "${templateType}" loaded successfully!`);
}

/**
 * Creates new schematic from scratch (no template).
 */
function createFromScratch() {
    const wellName = $('#select_well').val() || 'Well';

    $('#template_selection_modal').hide();
    resetAllData();
    schematicData.well.name = wellName;
    resetUI();
    populateWellConfigForms(schematicData);
    initializeNewSchematicEditor('Untitled schematic');
    showSchematicUI();
    showSuccessMessage('Ready to create new schematic from scratch!');
}

/**
 * Opens template selection for a new schematic.
 */
function createNewSchematic() {
    if (schematicDoc.isDirty) {
        confirmUnsavedIfNeeded(showTemplateSelection);
        return;
    }
    showTemplateSelection();
}

/**
 * Flushes in-progress unit edits into schematicData before save.
 */
function flushPendingUnitEditsBeforeSave() {
    syncFormToCurrentUnit(true);
    return true;
}

/**
 * Builds the payload written to disk.
 */
function buildDataToSave() {
    const well_name = $('#select_well').val();
    schematicData.well.name = well_name;
    syncWellConfigFromForm();
    const dataToSave = JSON.parse(JSON.stringify(schematicData));
    dataToSave.units = JSON.parse(JSON.stringify(schematicData.tubulars));
    return dataToSave;
}

/**
 * Persists schematic data under the given name.
 */
function performSaveSchematic(schematicName, options) {
    options = options || {};
    const well_name = $('#select_well').val();
    const safeName = sanitizeSchematicName(schematicName);

    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }
    if (!safeName) {
        showErrorMessage('Please enter a valid schematic name');
        return;
    }
    if (!flushPendingUnitEditsBeforeSave()) {
        return;
    }
    if (schematicData.tubulars.length === 0) {
        showErrorMessage('Please add at least one unit before saving');
        return;
    }

    const targetFilename = `${safeName}.json`;
    if (options.confirmOverwrite && schematicFilenameExists(targetFilename)) {
        const isSameFile = schematicDoc.filename === targetFilename;
        if (!isSameFile && !confirm(`A schematic named "${safeName}" already exists. Overwrite it?`)) {
            return;
        }
    }

    const dataToSave = buildDataToSave();

    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/save_schematic',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_name: safeName,
            schematic_data: dataToSave
        }),
        success: function () {
            showSuccessMessage('Schematic saved successfully!');
            $('#json_input_error').text('');
            setSchematicDocFromFile(targetFilename, safeName);
            checkForSavedSchematics(targetFilename);
            updateSchematicToolbar();
            if (options.onSuccess) {
                options.onSuccess();
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error ?
                `Error saving schematic: ${xhr.responseJSON.error}` :
                'Error saving schematic';
            $('#json_input_error').text(errorMsg);
            showErrorMessage(errorMsg);
        }
    });
}

/**
 * Saves the active schematic, prompting for a name when needed.
 */
function saveSchematic() {
    if (schematicDoc.filename) {
        performSaveSchematic(schematicDoc.displayName, { confirmOverwrite: false });
        return;
    }
    openSchematicNamePrompt('save');
}

/**
 * Saves the active schematic under a new name.
 */
function saveSchematicAs() {
    openSchematicNamePrompt('save_as');
}

/**
 * Opens the schematic name prompt modal.
 */
function openSchematicNamePrompt(mode) {
    namePromptMode = mode;
    const defaultName = mode === 'save_as'
        ? (schematicDoc.displayName ? `${schematicDoc.displayName} copy` : '')
        : (schematicDoc.displayName || '');
    $('#schematic_name_prompt_title').text(mode === 'save_as' ? 'Save Schematic As' : 'Save Schematic');
    $('#schematic_name_prompt_input').val(defaultName);
    $('#schematic_name_prompt_modal').show();
    $('#schematic_name_prompt_input').trigger('focus');
}

/**
 * Confirms schematic name prompt and saves.
 */
function confirmSchematicNamePrompt() {
    const schematicName = $('#schematic_name_prompt_input').val().trim();
    if (!schematicName) {
        showErrorMessage('Please enter a schematic name');
        return;
    }
    const mode = namePromptMode;
    const resumeAction = pendingNavigationAction;
    $('#schematic_name_prompt_modal').hide();
    namePromptMode = null;
    performSaveSchematic(schematicName, {
        confirmOverwrite: true,
        onSuccess: function () {
            pendingNavigationAction = null;
            if (mode === 'save_as') {
                showInfoMessage('Schematic saved under the new name.');
            }
            if (resumeAction && resumeAction.onProceed) {
                resumeAction.onProceed();
            }
        }
    });
}

/**
 * Handles Save from the unsaved-changes modal.
 */
function handleUnsavedChangesSave() {
    const action = pendingNavigationAction;
    $('#unsaved_changes_modal').hide();
    if (!action) {
        return;
    }
    if (schematicDoc.filename) {
        performSaveSchematic(schematicDoc.displayName, {
            confirmOverwrite: false,
            onSuccess: function () {
                pendingNavigationAction = null;
                action.onProceed();
            }
        });
    } else {
        openSchematicNamePrompt('save');
    }
}

/**
 * Handles Discard from the unsaved-changes modal.
 */
function handleUnsavedChangesDiscard() {
    const action = pendingNavigationAction;
    closeUnsavedChangesModal(false);
    if (action && action.onProceed) {
        schematicDoc.isDirty = false;
        action.onProceed();
    }
}

/**
 * Deletes the currently active saved schematic.
 */
function deleteCurrentSchematic() {
    const well_name = $('#select_well').val();
    const schematic_filename = schematicDoc.filename;

    if (!well_name || !schematic_filename) {
        showErrorMessage('No saved schematic is open');
        return;
    }

    const displayName = schematicDoc.displayName || schematic_filename;
    if (!confirm(`Delete schematic "${displayName}"? This cannot be undone.`)) {
        return;
    }

    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/delete_schematic',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function () {
            showSuccessMessage('Schematic deleted successfully!');
            resetSchematicDoc();
            resetAllData();
            resetUI();
            hideEditorCards();
            checkForSavedSchematics('');
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error ?
                `Error deleting schematic: ${xhr.responseJSON.error}` :
                'Error deleting schematic';
            showErrorMessage(errorMsg);
        }
    });
}

/**
 * Hides editor cards while keeping the toolbar visible.
 */
function hideEditorCards() {
    $('#well_schematics_input_card').hide();
    $('#schematic_output_card').hide();
    updateSchematicToolbar();
}

/**
 * Converts old format units to API format tubulars
 */
function convertOldFormatToApiFormat(units, wellName) {
    return units.map(unit => {
        const tubular = {
            name: unit.name,
            tubular_type: unit.type,
            top_depth: unit.top_depth,
            bottom_depth: unit.bottom_depth,
            inner_diameter: unit.inner_diameter,
            outer_diameter: unit.outer_diameter
        };
        
        if (unit.openhole_diameter) {
            tubular.openhole_diameter = unit.openhole_diameter;
        }
        
        // Handle new optional fields
        if (unit.hole_top_depth !== undefined) {
            tubular.hole_top_depth = unit.hole_top_depth;
        }
        if (unit.hole_bottom_depth !== undefined) {
            tubular.hole_bottom_depth = unit.hole_bottom_depth;
        }
        if (unit.draw_shoe !== undefined) {
            tubular.draw_shoe = unit.draw_shoe;
        }
        applyNumSealsToTubular(tubular, resolveNumSeals(unit));
        
        if (unit.type === 'casing' && unit.is_tapered) {
            tubular.tubular_type = 'tapered_casing';
            tubular.segments = [
                {
                    top_depth: unit.top_depth,
                    bottom_depth: unit.transition_depth,
                    inner_diameter: unit.inner_diameter,
                    outer_diameter: unit.outer_diameter
                },
                {
                    top_depth: unit.transition_depth,
                    bottom_depth: unit.bottom_depth,
                    inner_diameter: unit.bottom_inner_diameter,
                    outer_diameter: unit.bottom_outer_diameter
                }
            ];
            delete tubular.top_depth;
            delete tubular.bottom_depth;
            delete tubular.inner_diameter;
            delete tubular.outer_diameter;
        }
        
        const fluids = [];
        (unit.annulus_fluids || []).forEach(f => {
            fluids.push({
                fluid_type: f.fluid_type,
                top_depth: f.top_depth,
                bottom_depth: f.bottom_depth,
                location: 'outside'
            });
        });
        (unit.inner_fluids || []).forEach(f => {
            fluids.push({
                fluid_type: f.fluid_type,
                top_depth: f.top_depth,
                bottom_depth: f.bottom_depth,
                location: 'inside'
            });
        });
        if (fluids.length > 0) {
            tubular.fluids = fluids;
        }
        
        if (unit.packers && unit.packers.length > 0) {
            tubular.packers = unit.packers.map(p => ({
                packer_type: p.packer_type,
                top_depth: p.depth_interval?.top || p.top_depth,
                bottom_depth: p.depth_interval?.bottom || p.bottom_depth
            }));
        }
        
        if (unit.plugs && unit.plugs.length > 0) {
            tubular.plugs = unit.plugs.map(p => ({
                plug_type: p.type || p.plug_type,
                top_depth: p.depth_interval?.top || p.top_depth,
                bottom_depth: p.depth_interval?.bottom || p.bottom_depth
            }));
        }
        
        // Handle cements (new field)
        if (unit.cements && unit.cements.length > 0) {
            tubular.cements = unit.cements.map(c => ({
                cement_type: c.cement_type,
                location: c.location,
                top_depth: c.top_depth,
                bottom_depth: c.bottom_depth
            }));
        }
        
        // Handle screens (new field)
        if (unit.screens && unit.screens.length > 0) {
            tubular.screens = unit.screens.map(s => ({
                screen_type: s.screen_type,
                top_depth: s.top_depth,
                bottom_depth: s.bottom_depth
            }));
        }
        
        return tubular;
    });
}

/**
 * Populates form with loaded units and sets up UI
 */
function populateFormFromUnits() {
    updateUnitListDisplay();
    if (schematicData.tubulars.length > 0) {
        selectUnit(0);
    } else {
        currentUnitIndex = -1;
        disableFormFields();
        updateUnitEditorStatus();
    }
}

/**
 * Populates form fields with specific unit data (from API format)
 */
function populateFormWithUnit(unitIndex) {
    if (unitIndex < 0 || unitIndex >= schematicData.tubulars.length) return;
    
    const tubular = schematicData.tubulars[unitIndex];
    currentUnitIndex = unitIndex;
    
    // Populate basic fields
    $('#unit_type').val(tubular.tubular_type === 'tapered_casing' ? 'casing' : tubular.tubular_type);
    $('#unit_name').val(tubular.name);
    
    // Handle tapered casing
    if (tubular.tubular_type === 'tapered_casing' && tubular.segments) {
        $('#is_tapered').prop('checked', true).trigger('change');
        populateSegmentsTable(tubular.segments);
        const firstSegment = tubular.segments[0];
        const lastSegment = tubular.segments[tubular.segments.length - 1];
        $('#unit_top').val(firstSegment.top_depth);
        $('#unit_bottom').val(lastSegment.bottom_depth);
        $('#unit_id').val(firstSegment.inner_diameter);
        $('#unit_od').val(firstSegment.outer_diameter);
    } else {
        $('#is_tapered').prop('checked', false).trigger('change');
        $('#unit_top').val(tubular.top_depth);
        $('#unit_bottom').val(tubular.bottom_depth);
        $('#unit_id').val(tubular.inner_diameter);
        $('#unit_od').val(tubular.outer_diameter);
    }
    
    $('#unit_oh').val(tubular.openhole_diameter || '');
    $('#hole_top_depth').val(tubular.hole_top_depth || '');
    $('#hole_bottom_depth').val(tubular.hole_bottom_depth || '');
    
    // Populate draw_shoe, num_seals
    $('#draw_shoe').prop('checked', tubular.draw_shoe !== false);
    $('#num_seals').val(String(resolveNumSeals(tubular)));
    
    // Populate sub-elements
    populateSubElements(tubular);
    $('#unit_type').trigger('change');
    
    // Populate ESP (only for tubing)
    if (tubular.tubular_type === 'tubing') {
        if (tubular.esp && tubular.esp.enabled) {
            $('#esp_enabled').prop('checked', true);
            $('#esp_top_depth').val(tubular.esp.top_depth != null ? tubular.esp.top_depth : '');
            $('#esp_bottom_depth').val(tubular.esp.bottom_depth != null ? tubular.esp.bottom_depth : '');
            $('#esp_fields').show();
        } else {
            $('#esp_enabled').prop('checked', false);
            $('#esp_top_depth, #esp_bottom_depth').val('');
            $('#esp_fields').hide();
        }
    } else {
        $('#esp_enabled').prop('checked', false);
        $('#esp_fields').hide();
        $('#esp_top_depth, #esp_bottom_depth').val('');
    }
}

/**
 * Builds tubular data from form fields in API format, merging into existing tubular.
 */
function buildUnitDataFromForm(options) {
    options = options || {};
    const tubularType = $('#unit_type').val();
    if (!tubularType && !options.lenient) {
        return null;
    }

    const existing = hasActiveUnit() ? schematicData.tubulars[currentUnitIndex] : {};
    const tubular = JSON.parse(JSON.stringify(existing));
    const isTapered = tubularType === 'casing' && $('#is_tapered').is(':checked');

    if (tubularType) {
        tubular.name = $('#unit_name').val() || tubular.name || '';
        tubular.tubular_type = isTapered ? 'tapered_casing' : tubularType;
    }

    // -- tapered vs standard geometry -----
    if (isTapered) {
        const segments = buildSegmentsFromTable();
        if (segments.length >= 2) {
            tubular.segments = segments;
            delete tubular.top_depth;
            delete tubular.bottom_depth;
            delete tubular.inner_diameter;
            delete tubular.outer_diameter;
        } else if (!options.lenient) {
            showErrorMessage('Tapered casing requires at least two valid segments.');
            return null;
        }
    } else if (tubularType) {
        tubular.top_depth = parseFloat($('#unit_top').val());
        if (isNaN(tubular.top_depth)) {
            tubular.top_depth = existing.top_depth != null ? existing.top_depth : 0;
        }
        tubular.bottom_depth = parseFloat($('#unit_bottom').val());
        if (isNaN(tubular.bottom_depth)) {
            tubular.bottom_depth = existing.bottom_depth != null ? existing.bottom_depth : 1500;
        }
        tubular.inner_diameter = parseFloat($('#unit_id').val());
        if (isNaN(tubular.inner_diameter)) {
            tubular.inner_diameter = existing.inner_diameter != null ? existing.inner_diameter : 10;
        }
        tubular.outer_diameter = parseFloat($('#unit_od').val());
        if (isNaN(tubular.outer_diameter)) {
            tubular.outer_diameter = existing.outer_diameter != null ? existing.outer_diameter : 12;
        }
        delete tubular.segments;
    }

    if ($('#unit_oh').val() !== '') {
        tubular.openhole_diameter = parseFloat($('#unit_oh').val());
    } else if (!options.lenient) {
        delete tubular.openhole_diameter;
    }

    if ($('#hole_top_depth').val() !== '') {
        tubular.hole_top_depth = parseFloat($('#hole_top_depth').val());
    } else if (!options.lenient) {
        delete tubular.hole_top_depth;
    }

    if ($('#hole_bottom_depth').val() !== '') {
        tubular.hole_bottom_depth = parseFloat($('#hole_bottom_depth').val());
    } else if (!options.lenient) {
        delete tubular.hole_bottom_depth;
    }

    syncTubularFieldsFromForm(tubular);

    // -- ESP (tubing only) -----
    if (tubular.tubular_type === 'tubing' && $('#esp_enabled').is(':checked')) {
        const espTop = parseFloat($('#esp_top_depth').val());
        const espBottom = parseFloat($('#esp_bottom_depth').val());
        tubular.esp = {
            enabled: true,
            top_depth: isNaN(espTop) ? 0 : espTop,
            bottom_depth: isNaN(espBottom) ? 0 : espBottom
        };
    } else {
        delete tubular.esp;
    }

    return tubular;
}

/**
 * Populates sub-elements from tubular data (API format)
 */
function populateSubElements(tubular) {
    const fluidsLocal = tubular.fluids || [];
    const cementsLocal = tubular.cements || [];
    const packersLocal = (tubular.packers || []).map(p => ({
        packer_type: p.packer_type,
        top_depth: p.top_depth,
        bottom_depth: p.bottom_depth
    }));
    const plugsLocal = (tubular.plugs || []).map(p => ({
        plug_type: p.plug_type,
        top_depth: p.top_depth,
        bottom_depth: p.bottom_depth
    }));
    const screensLocal = tubular.screens || [];
    const perfsLocal = [];

    const rowClass = (type, i) => {
        const selected = hasActiveUnit() && selectedSubType === type && selectedSubIndex === i;
        return 'sub-element-row' + (selected ? ' selected' : '');
    };

    const deleteBtn = (removeFn, i) => hasActiveUnit()
        ? `<button type="button" class="btn btn-sm btn-danger" onclick="event.stopPropagation(); ${removeFn}(${i});" style="padding: 4px 8px; margin-left: 8px;"><i class="fa fa-trash"></i> Delete</button>`
        : '';

    if (fluidsLocal.length > 0) {
        $('#fluids_list').html(fluidsLocal.map((f, i) =>
            `<div class="${rowClass('fluid', i)}" onclick="selectFluid(${i})" title="Click to edit">
                <span class="sub-element-label">${i + 1}. ${f.fluid_type} (${f.location}) (${f.top_depth}-${f.bottom_depth})</span>
                ${deleteBtn('removeFluid', i)}
            </div>`
        ).join(''));
    } else {
        $('#fluids_list').html('<div class="sub-element-list-empty">No fluids added yet</div>');
    }

    if (cementsLocal.length > 0) {
        $('#cements_list').html(cementsLocal.map((c, i) =>
            `<div class="${rowClass('cement', i)}" onclick="selectCement(${i})" title="Click to edit">
                <span class="sub-element-label">${i + 1}. ${c.cement_type} (${c.location}) (${c.top_depth}-${c.bottom_depth})</span>
                ${deleteBtn('removeCement', i)}
            </div>`
        ).join(''));
    } else {
        $('#cements_list').html('<div class="sub-element-list-empty">No cements added yet</div>');
    }

    if (packersLocal.length > 0) {
        $('#packers_list').html(packersLocal.map((p, i) =>
            `<div class="${rowClass('packer', i)}" onclick="selectPacker(${i})" title="Click to edit">
                <span class="sub-element-label">${i + 1}. ${p.packer_type} (${p.top_depth}-${p.bottom_depth})</span>
                ${deleteBtn('removePacker', i)}
            </div>`
        ).join(''));
    } else {
        $('#packers_list').html('<div class="sub-element-list-empty">No packers added yet</div>');
    }

    if (plugsLocal.length > 0) {
        $('#plugs_list').html(plugsLocal.map((p, i) =>
            `<div class="${rowClass('plug', i)}" onclick="selectPlug(${i})" title="Click to edit">
                <span class="sub-element-label">${i + 1}. ${p.plug_type} (${p.top_depth}-${p.bottom_depth})</span>
                ${deleteBtn('removePlug', i)}
            </div>`
        ).join(''));
    } else {
        $('#plugs_list').html('<div class="sub-element-list-empty">No plugs added yet</div>');
    }

    if (screensLocal.length > 0) {
        $('#screens_list').html(screensLocal.map((s, i) =>
            `<div class="${rowClass('screen', i)}" onclick="selectScreen(${i})" title="Click to edit">
                <span class="sub-element-label">${i + 1}. ${s.screen_type} (${s.top_depth}-${s.bottom_depth})</span>
                ${deleteBtn('removeScreen', i)}
            </div>`
        ).join(''));
    } else {
        $('#screens_list').html('<div class="sub-element-list-empty">No screens added yet</div>');
    }

    if (perfsLocal.length > 0) {
        $('#perfs_list').html(perfsLocal.map((p, i) =>
            `<div class="sub-element-row">
                <span class="sub-element-label">${i + 1}. (${p.depth_interval.top}-${p.depth_interval.bottom}) Phases: ${p.phases}, Density: ${p.density}</span>
            </div>`
        ).join(''));
    } else {
        $('#perfs_list').html('<div class="sub-element-list-empty">No perforations added yet</div>');
    }

    updateAllSubElementEditorStatuses();
}

/**
 * Updates tapered casing segment defaults from unit fields.
 */
function updateTaperedFields() {
    if ($('#segments_table_body tr').length === 0) {
        initDefaultSegmentsFromUnitFields();
    }
}




// =============================================================================
// UNIT MANAGEMENT
// =============================================================================

/**
 * Returns the tubular currently selected for editing, or null.
 */
function getActiveTubular() {
    if (!hasActiveUnit()) {
        return null;
    }
    return schematicData.tubulars[currentUnitIndex];
}

/**
 * Updates the unit editor status line under the unit list.
 */
function updateUnitEditorStatus() {
    const $status = $('#unit_editor_status');
    if (!$status.length) {
        return;
    }
    if (!hasActiveUnit()) {
        $status.text('Select a unit to edit');
        return;
    }
    const tubular = schematicData.tubulars[currentUnitIndex];
    $status.text(`Editing: ${tubular.name || 'Unnamed unit'}`);
}

/**
 * Writes tubular form fields into schematicData.tubulars[currentUnitIndex].
 */
function syncFormToCurrentUnit(immediate) {
    if (unitFormSyncSuspended || !hasActiveUnit()) {
        return true;
    }

    const runSync = function() {
        unitFormSyncTimer = null;
        const tubular = buildUnitDataFromForm({ lenient: true });
        if (!tubular) {
            return;
        }
        schematicData.tubulars[currentUnitIndex] = tubular;
        setSchematicDirty(true);
        updateUnitListDisplay();
        updateUnitEditorStatus();
    };

    if (immediate) {
        if (unitFormSyncTimer) {
            clearTimeout(unitFormSyncTimer);
            unitFormSyncTimer = null;
        }
        runSync();
        return true;
    }

    if (unitFormSyncTimer) {
        clearTimeout(unitFormSyncTimer);
    }
    unitFormSyncTimer = setTimeout(runSync, 300);
    return true;
}

function scheduleFormSync() {
    syncFormToCurrentUnit(false);
}

/**
 * Selects a unit and loads its data into the form (click-to-edit).
 */
function selectUnit(unitIndex) {
    if (unitIndex === currentUnitIndex && hasActiveUnit()) {
        return;
    }

    syncFormToCurrentUnit(true);
    flushSelectedSubElementBeforeSwitch();

    if (unitIndex < 0 || unitIndex >= schematicData.tubulars.length) {
        currentUnitIndex = -1;
        clearSubSelection();
        clearFormFields();
        disableFormFields();
        updateUnitListDisplay();
        updateUnitEditorStatus();
        return;
    }

    currentUnitIndex = unitIndex;
    clearSubSelection();
    unitFormSyncSuspended = true;
    populateFormWithUnit(unitIndex);
    unitFormSyncSuspended = false;
    enableFormFields();
    updateUnitListDisplay();
    updateUnitEditorStatus();
}

/**
 * Appends a default stub tubular and selects it for editing.
 */
function addNewUnitStub() {
    syncFormToCurrentUnit(true);
    schematicData.tubulars.push({
        name: 'New unit',
        tubular_type: 'casing',
        top_depth: 0,
        bottom_depth: 1500,
        inner_diameter: 10,
        outer_diameter: 12,
        draw_shoe: true,
        has_spool: true,
        num_seals: 2
    });
    setSchematicDirty(true);
    selectUnit(schematicData.tubulars.length - 1);
}

/**
 * Deletes a unit after confirmation.
 */
function deleteUnitAt(unitIndex) {
    if (unitIndex < 0 || unitIndex >= schematicData.tubulars.length) {
        return;
    }

    const name = schematicData.tubulars[unitIndex].name || 'this unit';
    if (!confirm(`Delete unit "${name}"?`)) {
        return;
    }

    syncFormToCurrentUnit(true);
    schematicData.tubulars.splice(unitIndex, 1);
    setSchematicDirty(true);
    clearSubSelection();

    if (schematicData.tubulars.length === 0) {
        currentUnitIndex = -1;
        clearFormFields();
        disableFormFields();
        updateUnitListDisplay();
        updateUnitEditorStatus();
        return;
    }

    const newIndex = unitIndex >= schematicData.tubulars.length
        ? schematicData.tubulars.length - 1
        : unitIndex;
    selectUnit(newIndex);
}

/**
 * Updates unit list display with click-to-edit and per-row delete.
 */
function updateUnitListDisplay() {
    const $unitList = $('#unit_list');

    if (schematicData.tubulars.length === 0) {
        $unitList.html('<div class="sub-element-list-empty" style="padding: 20px;">No units defined yet. Click Add unit to get started.</div>');
        updateUnitEditorStatus();
        updateSchematicToolbar();
        return;
    }

    const html = schematicData.tubulars.map((tubular, index) => {
        const isSelected = index === currentUnitIndex;
        const selectedClass = isSelected ? ' selected' : '';

        let topDepth, bottomDepth, innerDiameter, outerDiameter;
        const isTapered = tubular.tubular_type === 'tapered_casing';
        if (isTapered && tubular.segments) {
            topDepth = tubular.segments[0].top_depth;
            bottomDepth = tubular.segments[tubular.segments.length - 1].bottom_depth;
            innerDiameter = tubular.segments[0].inner_diameter;
            outerDiameter = tubular.segments[0].outer_diameter;
        } else {
            topDepth = tubular.top_depth;
            bottomDepth = tubular.bottom_depth;
            innerDiameter = tubular.inner_diameter;
            outerDiameter = tubular.outer_diameter;
        }

        const fluidCount = (tubular.fluids || []).length;
        const cementCount = (tubular.cements || []).length;

        return `
            <div class="unit-item${selectedClass}" data-unit-index="${index}">
                <div style="flex: 1;">
                    <div class="unit-item-name">${tubular.name || 'Unnamed unit'}</div>
                    <div class="unit-item-meta">
                        <span class="badge badge-secondary">${tubular.tubular_type}</span>
                        <span style="margin-left: 10px;">${topDepth} - ${bottomDepth} m</span>
                    </div>
                    <div class="unit-item-detail" style="margin-top: 5px;">
                        ID: ${innerDiameter}" | OD: ${outerDiameter}"
                        ${isTapered ? ' | Tapered' : ''}
                    </div>
                    <div class="unit-item-detail">
                        Fluids: ${fluidCount} |
                        Cements: ${cementCount} |
                        Packers: ${tubular.packers?.length || 0} |
                        Plugs: ${tubular.plugs?.length || 0} |
                        Screens: ${tubular.screens?.length || 0}
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-danger unit-delete-btn" data-unit-index="${index}" title="Delete unit" style="margin-left: 8px; padding: 4px 8px; align-self: flex-start;">
                    <i class="fa fa-trash"></i> Delete
                </button>
            </div>
        `;
    }).join('');

    $unitList.html(html);

    $('.unit-item').off('click').on('click', function(e) {
        if ($(e.target).closest('.unit-delete-btn').length) {
            return;
        }
        selectUnit(parseInt($(this).data('unit-index'), 10));
    });

    $('.unit-delete-btn').off('click').on('click', function(e) {
        e.stopPropagation();
        deleteUnitAt(parseInt($(this).data('unit-index'), 10));
    });

    updateSchematicToolbar();
}

/**
 * Enables form fields for editing
 */
function enableFormFields() {
    $('#unit_type, #unit_name, #unit_top, #unit_bottom, #unit_id, #unit_od, #unit_oh, #hole_top_depth, #hole_bottom_depth, #draw_shoe, #num_seals, #esp_enabled, #esp_top_depth, #esp_bottom_depth, #fluid_type, #fluid_location, #fluid_top, #fluid_bottom, #fluid_density, #add_fluid_btn, #cement_type, #cement_location, #cement_top, #cement_bottom, #add_cement_btn, #packer_type, #packer_top, #packer_bottom, #add_packer_btn, #plug_plugtype, #plug_top, #plug_bottom, #add_plug_btn, #screen_type, #screen_top, #screen_bottom, #add_screen_btn, #add_segment_btn').prop('disabled', false);
    $('#is_tapered, #segments_table_body input, #segments_table_body button').prop('disabled', false);
}

/**
 * Disables form fields when no unit is selected
 */
function disableFormFields() {
    $('#unit_type, #unit_name, #unit_top, #unit_bottom, #unit_id, #unit_od, #unit_oh, #hole_top_depth, #hole_bottom_depth, #draw_shoe, #num_seals, #esp_enabled, #esp_top_depth, #esp_bottom_depth, #fluid_type, #fluid_location, #fluid_top, #fluid_bottom, #fluid_density, #add_fluid_btn, #cement_type, #cement_location, #cement_top, #cement_bottom, #add_cement_btn, #packer_type, #packer_top, #packer_bottom, #add_packer_btn, #plug_plugtype, #plug_top, #plug_bottom, #add_plug_btn, #screen_type, #screen_top, #screen_bottom, #add_screen_btn, #add_segment_btn').prop('disabled', true);
    $('#is_tapered, #segments_table_body input, #segments_table_body button').prop('disabled', true);
}

// =============================================================================
// SUB-ELEMENT MANAGEMENT
// =============================================================================

const SUB_ELEMENT_STATUS_IDS = {
    fluid: 'fluid_editor_status',
    cement: 'cement_editor_status',
    packer: 'packer_editor_status',
    plug: 'plug_editor_status',
    screen: 'screen_editor_status'
};

const SUB_ELEMENT_DEFAULT_STATUS = {
    fluid: 'Click a fluid to edit, or use Add Fluid',
    cement: 'Click a cement to edit, or use Add Cement',
    packer: 'Click a packer to edit, or use Add Packer',
    plug: 'Click a plug to edit, or use Add Plug',
    screen: 'Click a screen to edit, or use Add Screen'
};

/**
 * Returns the tubular array for a sub-element type.
 */
function getSubElementArray(tubular, type) {
    switch (type) {
        case 'fluid': return tubular.fluids || [];
        case 'cement': return tubular.cements || [];
        case 'packer': return tubular.packers || [];
        case 'plug': return tubular.plugs || [];
        case 'screen': return tubular.screens || [];
        default: return [];
    }
}

/**
 * Ensures the tubular has an array for the given sub-element type.
 */
function ensureSubElementArray(tubular, type) {
    switch (type) {
        case 'fluid':
            if (!tubular.fluids) { tubular.fluids = []; }
            return tubular.fluids;
        case 'cement':
            if (!tubular.cements) { tubular.cements = []; }
            return tubular.cements;
        case 'packer':
            if (!tubular.packers) { tubular.packers = []; }
            return tubular.packers;
        case 'plug':
            if (!tubular.plugs) { tubular.plugs = []; }
            return tubular.plugs;
        case 'screen':
            if (!tubular.screens) { tubular.screens = []; }
            return tubular.screens;
        default:
            return [];
    }
}

/**
 * Builds a sub-element object from the tab form fields, or null if invalid.
 */
function buildSubElementFromForm(type) {
    switch (type) {
        case 'fluid': {
            const fluid = {
                fluid_type: $('#fluid_type').val(),
                location: $('#fluid_location').val(),
                top_depth: parseFloat($('#fluid_top').val()),
                bottom_depth: parseFloat($('#fluid_bottom').val())
            };
            applyOptionalFluidFields(fluid);
            if (!fluid.fluid_type || !fluid.location || isNaN(fluid.top_depth) || isNaN(fluid.bottom_depth)) {
                return null;
            }
            return fluid;
        }
        case 'cement': {
            const cement = {
                cement_type: $('#cement_type').val(),
                location: $('#cement_location').val(),
                top_depth: parseFloat($('#cement_top').val()),
                bottom_depth: parseFloat($('#cement_bottom').val())
            };
            if (!cement.cement_type || !cement.location || isNaN(cement.top_depth) || isNaN(cement.bottom_depth)) {
                return null;
            }
            return cement;
        }
        case 'packer': {
            const packer = {
                packer_type: $('#packer_type').val(),
                top_depth: parseFloat($('#packer_top').val()),
                bottom_depth: parseFloat($('#packer_bottom').val())
            };
            if (!packer.packer_type || isNaN(packer.top_depth) || isNaN(packer.bottom_depth)) {
                return null;
            }
            return packer;
        }
        case 'plug': {
            const plug = {
                plug_type: $('#plug_plugtype').val(),
                top_depth: parseFloat($('#plug_top').val()),
                bottom_depth: parseFloat($('#plug_bottom').val())
            };
            if (!plug.plug_type || isNaN(plug.top_depth) || isNaN(plug.bottom_depth)) {
                return null;
            }
            return plug;
        }
        case 'screen': {
            const screen = {
                screen_type: $('#screen_type').val(),
                top_depth: parseFloat($('#screen_top').val()),
                bottom_depth: parseFloat($('#screen_bottom').val())
            };
            if (!screen.screen_type || isNaN(screen.top_depth) || isNaN(screen.bottom_depth)) {
                return null;
            }
            return screen;
        }
        default:
            return null;
    }
}

/**
 * Loads sub-element form fields from a tubular array entry.
 */
function loadSubElementFormFromEntry(type, entry) {
    switch (type) {
        case 'fluid':
            $('#fluid_type').val(entry.fluid_type);
            $('#fluid_location').val(entry.location || 'inside');
            $('#fluid_top').val(entry.top_depth);
            $('#fluid_bottom').val(entry.bottom_depth);
            $('#fluid_density').val(entry.density != null ? entry.density : '');
            break;
        case 'cement':
            $('#cement_type').val(entry.cement_type);
            $('#cement_location').val(entry.location || 'outside');
            $('#cement_top').val(entry.top_depth);
            $('#cement_bottom').val(entry.bottom_depth);
            break;
        case 'packer':
            $('#packer_type').val(entry.packer_type);
            $('#packer_top').val(entry.top_depth);
            $('#packer_bottom').val(entry.bottom_depth);
            break;
        case 'plug':
            $('#plug_plugtype').val(entry.plug_type);
            $('#plug_top').val(entry.top_depth);
            $('#plug_bottom').val(entry.bottom_depth);
            break;
        case 'screen':
            $('#screen_type').val(entry.screen_type);
            $('#screen_top').val(entry.top_depth);
            $('#screen_bottom').val(entry.bottom_depth);
            break;
    }
}

/**
 * Formats a sub-element entry for the editor status line.
 */
function formatSubElementLabel(type, entry) {
    switch (type) {
        case 'fluid':
            return `${entry.fluid_type} (${entry.location}) ${entry.top_depth}-${entry.bottom_depth} m`;
        case 'cement':
            return `${entry.cement_type} (${entry.location}) ${entry.top_depth}-${entry.bottom_depth} m`;
        case 'packer':
            return `${entry.packer_type} ${entry.top_depth}-${entry.bottom_depth} m`;
        case 'plug':
            return `${entry.plug_type} ${entry.top_depth}-${entry.bottom_depth} m`;
        case 'screen':
            return `${entry.screen_type} ${entry.top_depth}-${entry.bottom_depth} m`;
        default:
            return '';
    }
}

/**
 * Updates the status line for one sub-element tab.
 */
function updateSubElementEditorStatus(type) {
    const $status = $('#' + SUB_ELEMENT_STATUS_IDS[type]);
    if (!$status.length) {
        return;
    }
    if (!hasActiveUnit() || selectedSubType !== type || selectedSubIndex < 0) {
        $status.text(SUB_ELEMENT_DEFAULT_STATUS[type]);
        return;
    }
    const tubular = getActiveTubular();
    const arr = getSubElementArray(tubular, type);
    const entry = arr[selectedSubIndex];
    if (!entry) {
        $status.text(SUB_ELEMENT_DEFAULT_STATUS[type]);
        return;
    }
    $status.text(`Editing: ${formatSubElementLabel(type, entry)}`);
}

function updateAllSubElementEditorStatuses() {
    Object.keys(SUB_ELEMENT_STATUS_IDS).forEach(updateSubElementEditorStatus);
}

/**
 * Writes the active sub-element form into the selected tubular array entry.
 */
function syncSelectedSubElementFromForm(immediate) {
    if (subFormSyncSuspended || !hasActiveUnit() || selectedSubIndex < 0 || !selectedSubType) {
        return true;
    }

    const tubular = getActiveTubular();
    const arr = getSubElementArray(tubular, selectedSubType);
    if (selectedSubIndex >= arr.length) {
        return true;
    }

    const runSync = function() {
        subFormSyncTimer = null;
        const built = buildSubElementFromForm(selectedSubType);
        if (!built) {
            return;
        }
        ensureSubElementArray(tubular, selectedSubType)[selectedSubIndex] = built;
        syncTubularFieldsFromForm(tubular);
        setSchematicDirty(true);
        populateSubElements(tubular);
        updateUnitListDisplay();
    };

    if (immediate) {
        if (subFormSyncTimer) {
            clearTimeout(subFormSyncTimer);
            subFormSyncTimer = null;
        }
        runSync();
        return true;
    }

    if (subFormSyncTimer) {
        clearTimeout(subFormSyncTimer);
    }
    subFormSyncTimer = setTimeout(runSync, 300);
    return true;
}

function scheduleSubElementSync() {
    syncSelectedSubElementFromForm(false);
}

function flushSelectedSubElementBeforeSwitch() {
    syncSelectedSubElementFromForm(true);
}

/**
 * Selects a sub-element row and loads it into the tab form (click-to-edit).
 */
function selectSubElement(type, index) {
    if (!hasActiveUnit()) {
        return;
    }
    const tubular = getActiveTubular();
    const arr = getSubElementArray(tubular, type);
    if (index < 0 || index >= arr.length) {
        return;
    }
    if (selectedSubType === type && selectedSubIndex === index) {
        return;
    }

    flushSelectedSubElementBeforeSwitch();
    selectedSubType = type;
    selectedSubIndex = index;

    subFormSyncSuspended = true;
    loadSubElementFormFromEntry(type, arr[index]);
    subFormSyncSuspended = false;

    populateSubElements(tubular);
    updateAllSubElementEditorStatuses();
}

function selectFluid(index) { selectSubElement('fluid', index); }
function selectCement(index) { selectSubElement('cement', index); }
function selectPacker(index) { selectSubElement('packer', index); }
function selectPlug(index) { selectSubElement('plug', index); }
function selectScreen(index) { selectSubElement('screen', index); }

/**
 * Adds fluid to the active unit.
 */
function addFluid() {
    const tubular = getActiveTubular();
    if (!tubular) {
        showErrorMessage('Select a unit first');
        return;
    }

    flushSelectedSubElementBeforeSwitch();
    const fluid = buildSubElementFromForm('fluid');
    if (!fluid) {
        showErrorMessage('Please fill in all fluid fields');
        return;
    }

    ensureSubElementArray(tubular, 'fluid').push(fluid);
    syncTubularFieldsFromForm(tubular);
    clearSubSelection();
    clearFluidFields();
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function addCement() {
    const tubular = getActiveTubular();
    if (!tubular) {
        showErrorMessage('Select a unit first');
        return;
    }

    flushSelectedSubElementBeforeSwitch();
    const cement = buildSubElementFromForm('cement');
    if (!cement) {
        showErrorMessage('Please fill in all cement fields');
        return;
    }

    ensureSubElementArray(tubular, 'cement').push(cement);
    syncTubularFieldsFromForm(tubular);
    clearSubSelection();
    clearCementFields();
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function addPacker() {
    const tubular = getActiveTubular();
    if (!tubular) {
        showErrorMessage('Select a unit first');
        return;
    }

    flushSelectedSubElementBeforeSwitch();
    const packer = buildSubElementFromForm('packer');
    if (!packer) {
        showErrorMessage('Please fill in all packer fields');
        return;
    }

    ensureSubElementArray(tubular, 'packer').push(packer);
    syncTubularFieldsFromForm(tubular);
    clearSubSelection();
    clearPackerFields();
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function addPlug() {
    const tubular = getActiveTubular();
    if (!tubular) {
        showErrorMessage('Select a unit first');
        return;
    }

    flushSelectedSubElementBeforeSwitch();
    const plug = buildSubElementFromForm('plug');
    if (!plug) {
        showErrorMessage('Please fill in all plug fields');
        return;
    }

    ensureSubElementArray(tubular, 'plug').push(plug);
    syncTubularFieldsFromForm(tubular);
    clearSubSelection();
    clearPlugFields();
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function addScreen() {
    const tubular = getActiveTubular();
    if (!tubular) {
        showErrorMessage('Select a unit first');
        return;
    }

    flushSelectedSubElementBeforeSwitch();
    const screen = buildSubElementFromForm('screen');
    if (!screen) {
        showErrorMessage('Please fill in all screen fields');
        return;
    }

    ensureSubElementArray(tubular, 'screen').push(screen);
    syncTubularFieldsFromForm(tubular);
    clearSubSelection();
    clearScreenFields();
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

/**
 * Adds perforation to current unit or temporary array
 */
function addPerforation() {
    showErrorMessage('Perforations are not supported in the current schematic format.');
}

function removeFluid(index) {
    const tubular = getActiveTubular();
    if (!tubular || !tubular.fluids || tubular.fluids.length <= index) {
        return;
    }
    if (selectedSubType === 'fluid' && selectedSubIndex === index) {
        clearSubSelection();
        clearFluidFields();
    } else if (selectedSubType === 'fluid' && selectedSubIndex > index) {
        selectedSubIndex--;
    }
    tubular.fluids.splice(index, 1);
    syncTubularFieldsFromForm(tubular);
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function removeCement(index) {
    const tubular = getActiveTubular();
    if (!tubular || !tubular.cements || tubular.cements.length <= index) {
        return;
    }
    if (selectedSubType === 'cement' && selectedSubIndex === index) {
        clearSubSelection();
        clearCementFields();
    } else if (selectedSubType === 'cement' && selectedSubIndex > index) {
        selectedSubIndex--;
    }
    tubular.cements.splice(index, 1);
    syncTubularFieldsFromForm(tubular);
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function removePacker(index) {
    const tubular = getActiveTubular();
    if (!tubular || !tubular.packers || tubular.packers.length <= index) {
        return;
    }
    if (selectedSubType === 'packer' && selectedSubIndex === index) {
        clearSubSelection();
        clearPackerFields();
    } else if (selectedSubType === 'packer' && selectedSubIndex > index) {
        selectedSubIndex--;
    }
    tubular.packers.splice(index, 1);
    syncTubularFieldsFromForm(tubular);
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function removePlug(index) {
    const tubular = getActiveTubular();
    if (!tubular || !tubular.plugs || tubular.plugs.length <= index) {
        return;
    }
    if (selectedSubType === 'plug' && selectedSubIndex === index) {
        clearSubSelection();
        clearPlugFields();
    } else if (selectedSubType === 'plug' && selectedSubIndex > index) {
        selectedSubIndex--;
    }
    tubular.plugs.splice(index, 1);
    syncTubularFieldsFromForm(tubular);
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function removeScreen(index) {
    const tubular = getActiveTubular();
    if (!tubular || !tubular.screens || tubular.screens.length <= index) {
        return;
    }
    if (selectedSubType === 'screen' && selectedSubIndex === index) {
        clearSubSelection();
        clearScreenFields();
    } else if (selectedSubType === 'screen' && selectedSubIndex > index) {
        selectedSubIndex--;
    }
    tubular.screens.splice(index, 1);
    syncTubularFieldsFromForm(tubular);
    populateSubElements(tubular);
    setSchematicDirty(true);
    updateUnitListDisplay();
}

function removePerforation(index) {
    showErrorMessage('Perforations are not supported in the current schematic format.');
}

function clearSubSelection() {
    selectedSubType = null;
    selectedSubIndex = -1;
    updateAllSubElementEditorStatuses();
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================



/**
 * Gets analysis parameters from form
 */
function getAnalysisParams() {
    return {
        well_name: $('#select_well').val(),
        starttime: $('#starttime').val(),
        endtime: $('#endtime').val()
    };
}

/**
 * Shows success message as a pop-up notification
 */
// =============================================================================
// TOAST NOTIFICATION SYSTEM
// =============================================================================

function showToast(message, type = 'success', duration = 4000) {
    const icons = {
        success: '✓',
        error: '✗',
        info: 'ℹ'
    };
    
    const toastDiv = $(`
        <div class="toast-notification ${type}">
            <span class="toast-icon">${icons[type] || icons.success}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="closeToast(this)">×</button>
        </div>
    `);
    
    $('#toast-container').append(toastDiv);
    
    // Trigger animation
    setTimeout(() => {
        toastDiv.addClass('show');
    }, 100);
    
    // Auto-remove after duration
    setTimeout(() => {
        removeToast(toastDiv);
    }, duration);
}

// Global function for closing toasts
window.closeToast = function(button) {
    const toast = $(button).closest('.toast-notification');
    removeToast(toast);
};

function removeToast(toast) {
    toast.addClass('fade-out');
    setTimeout(() => {
        toast.remove();
    }, 300);
}

function showSuccessMessage(message) {
    showToast(message, 'success');
}

function showErrorMessage(message) {
    showToast(message, 'error');
}

function showInfoMessage(message) {
    showToast(message, 'info');
}

/**
 * Shows schematic UI elements
 */
function showSchematicUI() {
    $('#well_schematics_input_card').show();
    $('#schematic_output_card').show();
    updateUnitListDisplay();
    updateUnitEditorStatus();
    updateSchematicToolbar();
}

/**
 * Hides all schematic UI elements
 */
function hideAllSchematicUI() {
    hideEditorCards();
    resetSchematicDoc();
    savedSchematicList = [];
    populateSchematicDropdown('');
    updateSchematicToolbar();
}

/**
 * Resets all data arrays
 */
function resetAllData() {
    const wellName = $('#select_well').val() || 'Well';
    schematicData = {
        well: {
            name: wellName,
            layout: {
                mode: "uniform",
                uniform_width: 0.1,
                uniform_spacing: 0.2,
                show_axes: true
            }
        },
        tubulars: []
    };
    currentUnitIndex = -1;
    unitFormSyncSuspended = false;
    if (unitFormSyncTimer) {
        clearTimeout(unitFormSyncTimer);
        unitFormSyncTimer = null;
    }
}

/**
 * Resets UI elements
 */
function resetUI() {
    $('#unit_list').html('<div class="sub-element-list-empty" style="padding: 20px;">No units defined yet. Click Add unit to get started.</div>');
    $('#well_schematic_output').html('');
    $('#unit_editor_status').text('Select a unit to edit');
    $('#unit_selector').empty().append('<option value="">Select a unit...</option>');
}

/**
 * Clears form fields
 */
function clearFormFields() {
    $('#unit_name, #unit_top, #unit_bottom, #unit_id, #unit_od, #unit_oh, #hole_top_depth, #hole_bottom_depth').val('');
    $('#unit_type').val('');
    $('#is_tapered').prop('checked', false).trigger('change');
    $('#segments_table_body').empty();
    $('#draw_shoe').prop('checked', true);
    $('#num_seals').val('2');
    $('#esp_enabled').prop('checked', false);
    $('#esp_top_depth, #esp_bottom_depth').val('');
    $('#esp_section, #esp_fields').hide();
    clearAllSubElementFields();
}

/**
 * Clears all sub-element input fields
 */
function clearAllSubElementFields() {
        clearFluidFields();
        clearCementFields();
        clearPackerFields();
        clearPlugFields();
        clearScreenFields();
        clearPerfFields();
}

// Field clearing functions
function clearFluidFields() {
    $('#fluid_type, #fluid_location, #fluid_top, #fluid_bottom, #fluid_density').val('');
    $('#fluid_location').val('inside'); // Reset to default
}

function clearCementFields() {
    $('#cement_type, #cement_location, #cement_top, #cement_bottom').val('');
    $('#cement_location').val('outside'); // Reset to default (cements are usually outside)
}

function clearPackerFields() {
    $('#packer_type, #packer_top, #packer_bottom').val('');
}

function clearPlugFields() {
    $('#plug_type, #plug_top, #plug_bottom, #plug_plugtype').val('');
}

function clearScreenFields() {
    $('#screen_type, #screen_top, #screen_bottom').val('');
}

function clearPerfFields() {
    $('#perf_top, #perf_bottom, #perf_phases, #perf_density').val('');
}

// =============================================================================
// WELLHEAD AND XMAS TREE CONFIGURATION
// =============================================================================

/**
 * Builds wellhead valves configuration from form
 */
function buildWellheadValvesConfig() {
    const wellheadValves = {
        enabled: $('#wellhead_valves_enabled').is(':checked')
    };
    
    if (!wellheadValves.enabled) {
        return wellheadValves;
    }

    wellheadValves.show_seals = $('#wellhead_show_seals').is(':checked');

    const includeLegacyRings = $('#wellhead_legacy_section').is(':visible') || hasLegacyWellheadRingConfig();
    if (!includeLegacyRings) {
        return wellheadValves;
    }

    ['A', 'B', 'C', 'D'].forEach(ringId => {
        const ring = buildWellheadRingConfig(ringId);
        if (ring) {
            wellheadValves[ringId] = ring;
        }
    });
    
    return wellheadValves;
}

/**
 * Builds layout configuration from General tab form
 */
function buildLayoutConfig() {
    const mode = $('#layout_mode').val() || 'uniform';
    const uniformWidth = parseFloat($('#layout_uniform_width').val());
    const uniformSpacing = parseFloat($('#layout_uniform_spacing').val());
    const figureWidth = parseFloat($('#layout_figure_width').val());
    const figureHeight = parseFloat($('#layout_figure_height').val());

    const layout = {
        mode: mode === 'depth_transformed' ? 'depth_transformed' : 'uniform',
        uniform_width: !isNaN(uniformWidth) ? uniformWidth : 0.1,
        uniform_spacing: !isNaN(uniformSpacing) ? uniformSpacing : 0.2,
        show_axes: $('#layout_show_axes').is(':checked')
    };
    if (!isNaN(figureWidth) && !isNaN(figureHeight)) {
        layout.figure_size = [figureWidth, figureHeight];
    }
    return layout;
}

/**
 * Populates General tab form from layout data
 */
function populateLayoutForm(layout) {
    if (!layout) {
        return;
    }
    $('#layout_mode').val(layout.mode === 'depth_transformed' ? 'depth_transformed' : 'uniform');
    $('#layout_uniform_width').val(layout.uniform_width != null ? layout.uniform_width : '');
    $('#layout_uniform_spacing').val(layout.uniform_spacing != null ? layout.uniform_spacing : '');
    const fig = layout.figure_size;
    $('#layout_figure_width').val(fig && fig[0] != null ? fig[0] : '');
    $('#layout_figure_height').val(fig && fig[1] != null ? fig[1] : '');
    $('#layout_show_axes').prop('checked', layout.show_axes !== false);
}

/**
 * Builds Xmas tree configuration from form
 */
function buildXmasTreeConfig() {
    const xmasTree = {
        enabled: $('#xmas_tree_enabled').is(':checked')
    };
    
    if (!xmasTree.enabled) {
        return xmasTree;
    }
    
    xmasTree.include_lower_master = $('#xmas_tree_lower_master').is(':checked');
    xmasTree.include_upper_master = $('#xmas_tree_upper_master').is(':checked');
    xmasTree.include_swab = $('#xmas_tree_swab').is(':checked');
    xmasTree.include_wings = $('#xmas_tree_wings').is(':checked');
    xmasTree.include_left_wing = $('#xmas_tree_left_wing').is(':checked');
    xmasTree.include_right_wing = $('#xmas_tree_right_wing').is(':checked');
    
    return xmasTree;
}

/**
 * Builds caprock configuration from form.
 */
function buildCaprockConfig() {
    if (!$('#caprock_enabled').is(':checked')) {
        return null;
    }
    const caprock = { enabled: true };
    const topDepth = parseFloat($('#caprock_top_depth').val());
    const bottomDepth = parseFloat($('#caprock_bottom_depth').val());
    if (!isNaN(topDepth)) {
        caprock.top_depth = topDepth;
    }
    if (!isNaN(bottomDepth)) {
        caprock.bottom_depth = bottomDepth;
    }
    const hatch = $('#caprock_hatch').val();
    if (hatch) {
        caprock.hatch = hatch;
    }
    return caprock;
}

/**
 * Populates caprock form from data.
 */
function populateCaprockForm(caprock) {
    if (!caprock || caprock.enabled === false) {
        resetCaprockForm();
        return;
    }
    $('#caprock_enabled').prop('checked', true);
    $('#caprock_fields').show();
    $('#caprock_top_depth').val(caprock.top_depth != null ? caprock.top_depth : '');
    $('#caprock_bottom_depth').val(caprock.bottom_depth != null ? caprock.bottom_depth : '');
    $('#caprock_hatch').val(caprock.hatch || '--');
}

/**
 * Resets caprock form to defaults.
 */
function resetCaprockForm() {
    $('#caprock_enabled').prop('checked', false);
    $('#caprock_fields').hide();
    $('#caprock_top_depth, #caprock_bottom_depth').val('');
    $('#caprock_hatch').val('--');
}

/**
 * Resets wellhead form to new-schema defaults (no legacy per-ring config).
 */
function resetWellheadFormDefaults() {
    $('#wellhead_valves_enabled').prop('checked', true);
    $('#wellhead_show_seals').prop('checked', true);
    $('#wellhead_a_enabled, #wellhead_b_enabled, #wellhead_c_enabled, #wellhead_d_enabled').prop('checked', false);
    $('#wellhead_a_left_valves, #wellhead_b_left_valves, #wellhead_c_left_valves, #wellhead_d_left_valves').prop('checked', false);
    $('#wellhead_a_right_valves, #wellhead_b_right_valves, #wellhead_c_right_valves, #wellhead_d_right_valves').prop('checked', false);
    setWellheadLegacySectionVisible(false);
}

/**
 * Populates wellhead valves form from data
 */
function populateWellheadValvesForm(wellheadValves) {
    if (!wellheadValves) {
        return;
    }
    
    $('#wellhead_valves_enabled').prop('checked', wellheadValves.enabled !== false);
    $('#wellhead_show_seals').prop('checked', wellheadValves.show_seals !== false);

    const hasLegacyRings = !!(wellheadValves.A || wellheadValves.B || wellheadValves.C || wellheadValves.D);
    if (hasLegacyRings) {
        setWellheadLegacySectionVisible(true);
    } else {
        setWellheadLegacySectionVisible(false);
    }
    
    if (wellheadValves.A) {
        populateWellheadRingForm('A', wellheadValves.A);
    }
    
    if (wellheadValves.B) {
        populateWellheadRingForm('B', wellheadValves.B);
    }
    
    if (wellheadValves.C) {
        populateWellheadRingForm('C', wellheadValves.C);
    }
    
    if (wellheadValves.D) {
        populateWellheadRingForm('D', wellheadValves.D);
    }
}

/**
 * Populates Xmas tree form from data
 */
function populateXmasTreeForm(xmasTree) {
    if (!xmasTree) {
        return;
    }
    
    $('#xmas_tree_enabled').prop('checked', xmasTree.enabled !== false);
    $('#xmas_tree_lower_master').prop('checked', xmasTree.include_lower_master || false);
    $('#xmas_tree_upper_master').prop('checked', xmasTree.include_upper_master !== false);
    $('#xmas_tree_swab').prop('checked', xmasTree.include_swab !== false);
    $('#xmas_tree_wings').prop('checked', xmasTree.include_wings !== false);
    $('#xmas_tree_left_wing').prop('checked', xmasTree.include_left_wing !== false);
    $('#xmas_tree_right_wing').prop('checked', xmasTree.include_right_wing || false);
    updateXmasTreeFormVisibility();
}

/**
 * Shows or hides X-mas tree valve options based on enabled / wings checkboxes.
 */
function updateXmasTreeFormVisibility() {
    const treeEnabled = $('#xmas_tree_enabled').is(':checked');
    $('#xmas_tree_valve_section').toggle(treeEnabled);

    const wingsEnabled = treeEnabled && $('#xmas_tree_wings').is(':checked');
    $('#xmas_tree_wing_section').toggle(wingsEnabled);
}

// =============================================================================
// SCHEMATIC GENERATION
// =============================================================================

// transformToApiFormat function removed - data is now stored directly in API format

/**
 * Generates schematic from current data using external backend API
 */
function generateSchematic() {
    $('#json_input_error').text('');
    $('#well_schematic_output').html('<span style="color:gray">Generating schematic...</span>');
    
    if (schematicData.tubulars.length === 0) {
        $('#json_input_error').text('No units defined. Please add units first or load a saved schematic.');
        $('#well_schematic_output').html('');
        return;
    }
    
    // Update well name in schematic data
    const wellName = $('#select_well').val() || 'Well';
    schematicData.well.name = wellName;
    syncWellConfigFromForm();

    // Data is already in API format
    const apiData = schematicData;
    
    $.ajax({
        url: '/app/well_schematics/generate_schematic',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(JSON.parse(JSON.stringify(apiData))), // Deep clone
        success: function(response) {
            // Show the schematic output card
            $('#schematic_output_card').show();
            $('#schematic_output_card_body').slideDown();
            
            if (response.image_base64) {
                $('#well_schematic_output').html(
                    `<img src="data:image/png;base64,${response.image_base64}" style="max-width:100%; height:auto; display: block;" />`
                );
            } else if (response.error) {
                $('#well_schematic_output').html(`<span style="color:red">${response.error}</span>`);
            } else {
                $('#well_schematic_output').html('<span style="color:red">No schematic returned.</span>');
            }
        },
        error: function(xhr) {
            let msg = 'Error generating schematic.';
            if (xhr.status === 0 || xhr.status === 503) {
                msg = 'Cannot connect to schematic generation server. Please ensure the backend server is running at http://localhost:8001';
            } else if (xhr.responseJSON?.error) {
                msg = `Error: ${xhr.responseJSON.error}`;
            } else if (xhr.statusText) {
                msg = `Error: ${xhr.statusText}`;
            }
            $('#well_schematic_output').html(`<span style="color:red">${msg}</span>`);
        }
    });
}

// =============================================================================
// EVENT HANDLERS
// =============================================================================

/**
 * Marks schematic dirty when well-level configuration fields change.
 */
function bindSchematicDirtyTracking() {
    const wellLevelSelector = [
        '#layout_mode', '#layout_uniform_width', '#layout_uniform_spacing',
        '#layout_figure_width', '#layout_figure_height', '#layout_show_axes',
        '#caprock_enabled', '#caprock_top_depth', '#caprock_bottom_depth', '#caprock_hatch',
        '#wellhead_valves_enabled', '#wellhead_show_seals',
        '#wellhead_a_enabled', '#wellhead_a_left_valves', '#wellhead_a_right_valves',
        '#wellhead_b_enabled', '#wellhead_b_left_valves', '#wellhead_b_right_valves',
        '#wellhead_c_enabled', '#wellhead_c_left_valves', '#wellhead_c_right_valves',
        '#wellhead_d_enabled', '#wellhead_d_left_valves', '#wellhead_d_right_valves',
        '#xmas_tree_enabled', '#xmas_tree_lower_master', '#xmas_tree_upper_master',
        '#xmas_tree_swab', '#xmas_tree_wings', '#xmas_tree_left_wing', '#xmas_tree_right_wing'
    ].join(', ');

    $(document).on('change input', wellLevelSelector, function () {
        if (schematicDoc.isLoading) {
            return;
        }
        if ($('#well_schematics_input_card').is(':visible')) {
            setSchematicDirty(true);
        }
    });
}

$(document).ready(function() {
    bindSchematicDirtyTracking();

    $('#select_well').on('focus', function () {
        previousWellValue = $(this).val() || '';
    });

    // Well selection change
    $('#select_well').on('change', onWellSelectChange);

    // Schematic selection auto-load
    $('#saved_schematics_select').on('change', onSchematicSelectChange);

    // Legacy wellhead per-ring section toggle
    $('#wellhead_legacy_toggle').on('click', function() {
        const isVisible = $('#wellhead_legacy_section').is(':visible');
        setWellheadLegacySectionVisible(!isVisible);
    });
    
    // Schematic toolbar actions
    $('#new_schematic_btn').on('click', createNewSchematic);
    $('#save_schematic_btn').on('click', saveSchematic);
    $('#save_as_schematic_btn').on('click', saveSchematicAs);
    $('#delete_schematic_btn').on('click', deleteCurrentSchematic);
    $('#generate_schematic_btn').on('click', generateSchematic);

    // Name prompt modal
    $('#schematic_name_prompt_save_btn').on('click', confirmSchematicNamePrompt);
    $('#schematic_name_prompt_cancel_btn').on('click', function () {
        $('#schematic_name_prompt_modal').hide();
        namePromptMode = null;
        if (pendingNavigationAction) {
            $('#unsaved_changes_modal').show();
        }
    });
    $('#schematic_name_prompt_input').on('keydown', function (e) {
        if (e.key === 'Enter') {
            confirmSchematicNamePrompt();
        }
    });

    // Unsaved changes modal
    $('#unsaved_changes_save_btn').on('click', handleUnsavedChangesSave);
    $('#unsaved_changes_discard_btn').on('click', handleUnsavedChangesDiscard);
    $('#unsaved_changes_cancel_btn').on('click', function () {
        closeUnsavedChangesModal(true);
    });

    // Template selection
    $('.template-card').on('click', function() {
        const templateType = $(this).data('template');
        $('.template-card').removeClass('selected');
        $(this).addClass('selected');
        
        if (templateType === 'scratch') {
            createFromScratch();
        } else {
            loadTemplate(templateType);
        }
    });
    
    $('#cancel_template_selection_btn').on('click', function() {
        $('#template_selection_modal').hide();
        suppressSchematicSelectChange = true;
        if (previousSchematicValue && previousSchematicValue !== SCHEMATIC_NEW_OPTION) {
            $('#saved_schematics_select').val(previousSchematicValue);
        } else {
            $('#saved_schematics_select').val('');
        }
        suppressSchematicSelectChange = false;
    });
    
    // Close modal when clicking outside
    $('#template_selection_modal').on('click', function(e) {
        if ($(e.target).is('#template_selection_modal')) {
            $('#cancel_template_selection_btn').trigger('click');
        }
    });
    
    // Unit management — click-to-edit with auto-sync
    $('#new_unit_btn').on('click', addNewUnitStub);

    const unitFormSyncSelectors = [
        '#unit_type', '#unit_name', '#unit_top', '#unit_bottom', '#unit_id', '#unit_od',
        '#unit_oh', '#hole_top_depth', '#hole_bottom_depth', '#draw_shoe', '#num_seals',
        '#esp_enabled', '#esp_top_depth', '#esp_bottom_depth', '#is_tapered'
    ].join(', ');
    $(document).on('input change', unitFormSyncSelectors, scheduleFormSync);
    $('#segments_table_body').on('input change', 'input', scheduleFormSync);
    
    // Sub-element management
    $('#add_fluid_btn').on('click', addFluid);
    $('#add_cement_btn').on('click', addCement);
    $('#add_packer_btn').on('click', addPacker);
    $('#add_plug_btn').on('click', addPlug);
    $('#add_screen_btn').on('click', addScreen);
    $('#add_perf_btn').on('click', addPerforation);

    const subElementSyncSelectors = [
        '#fluid_type', '#fluid_location', '#fluid_top', '#fluid_bottom', '#fluid_density',
        '#cement_type', '#cement_location', '#cement_top', '#cement_bottom',
        '#packer_type', '#packer_top', '#packer_bottom',
        '#plug_plugtype', '#plug_top', '#plug_bottom',
        '#screen_type', '#screen_top', '#screen_bottom'
    ].join(', ');
    $(document).on('input change', subElementSyncSelectors, scheduleSubElementSync);
    
    // Unit type change
    $('#unit_type').on('change', function() {
        const val = $(this).val();
        if (val === 'casing') {
            $('#tapered_casing_section').show();
            $('#esp_section').hide();
            $('#esp_enabled').prop('checked', false);
            $('#esp_fields').hide();
        } else if (val === 'tubing') {
            $('#tapered_casing_section').hide();
            $('#is_tapered').prop('checked', false).trigger('change');
            $('#esp_section').show();
        } else {
            $('#tapered_casing_section').hide();
            $('#is_tapered').prop('checked', false).trigger('change');
            $('#esp_section').hide();
            $('#esp_enabled').prop('checked', false);
            $('#esp_fields').hide();
        }
        scheduleFormSync();
    });
    
    // ESP checkbox - show/hide depth fields
    $('#esp_enabled').on('change', function() {
        if ($(this).is(':checked')) {
            $('#esp_fields').show();
        } else {
            $('#esp_fields').hide();
            $('#esp_top_depth, #esp_bottom_depth').val('');
        }
        scheduleFormSync();
    });
    
    // Tapered casing checkbox
    $('#is_tapered').on('change', function() {
        if ($(this).is(':checked')) {
            $('#tapered_fields').show();
            if ($('#segments_table_body tr').length === 0) {
                initDefaultSegmentsFromUnitFields();
            }
        } else {
            $('#tapered_fields').hide();
            $('#segments_table_body').empty();
        }
        scheduleFormSync();
    });

    $('#add_segment_btn').on('click', function() {
        const rows = $('#segments_table_body tr');
        const lastRow = rows.last();
        const lastBottom = lastRow.length ? parseFloat(lastRow.find('.seg-bottom').val()) : NaN;
        addSegmentRow({
            top_depth: !isNaN(lastBottom) ? lastBottom : '',
            bottom_depth: '',
            inner_diameter: lastRow.length ? lastRow.find('.seg-id').val() : '',
            outer_diameter: lastRow.length ? lastRow.find('.seg-od').val() : ''
        });
        scheduleFormSync();
    });

    $('#segments_table_body').on('click', '.remove-segment-btn', function() {
        if ($('#segments_table_body tr').length <= 2) {
            return;
        }
        $(this).closest('tr').remove();
        updateSegmentRemoveButtons();
        scheduleFormSync();
    });

    $('#caprock_enabled').on('change', function() {
        if ($(this).is(':checked')) {
            $('#caprock_fields').slideDown();
        } else {
            $('#caprock_fields').slideUp();
        }
    });

    $('#xmas_tree_enabled, #xmas_tree_wings').on('change', updateXmasTreeFormVisibility);
    
    // Auto-update tapered fields
    $('#unit_top, #unit_bottom').on('input', function() {
        if ($('#is_tapered').is(':checked')) {
            updateTaperedFields();
        }
    });
    
    $('#unit_id, #unit_od').on('input', function() {
        if ($('#is_tapered').is(':checked')) {
            updateTaperedFields();
        }
    });
    
    // Toggle Schematic card collapse/expand
    $('#toggle_schematic_card_btn').on('click', function() {
        const $body = $('#schematic_output_card_body');
        const $icon = $('#schematic_card_toggle_icon');
        if ($body.is(':visible')) {
            $body.slideUp();
            $icon.removeClass('fa-chevron-up').addClass('fa-chevron-down');
        } else {
            $body.slideDown();
            $icon.removeClass('fa-chevron-down').addClass('fa-chevron-up');
        }
    });

    // Initialize
    $('#unit_type').trigger('change');
    populateWellConfigForms(schematicData);
    updateXmasTreeFormVisibility();
    updateSchematicToolbar();
});