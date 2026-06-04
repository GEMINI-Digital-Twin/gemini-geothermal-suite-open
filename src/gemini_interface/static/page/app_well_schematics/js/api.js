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
            uniform_spacing: 0.2
        }
    },
    tubulars: []
};
let currentUnitIndex = -1; // -1 means no unit selected
let currentMode = 'none'; // 'none', 'creation', 'editing'
let progressInterval;

// Temporary storage for sub-elements during unit creation
let tempFluids = []; // Combined fluids with location
let tempCements = []; // Cements with location
let tempPackers = [];
let tempPlugs = [];
let tempScreens = [];
let tempPerforations = [];

// Selected sub-component when editing (for updating existing item)
let selectedSubType = null; // 'fluid' | 'cement' | 'packer' | 'plug' | 'screen'
let selectedSubIndex = -1;

// =============================================================================
// TEMPLATE DEFINITIONS
// =============================================================================

/**
 * Returns template 1: Simple Well (Conductor + Tubing)
 */
function getSimpleWellTemplate(wellName) {
    return {
        well: {
            name: wellName || "Well",
            layout: {
                mode: "uniform",
                uniform_width: 0.1,
                uniform_spacing: 0.2
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
                hanger_seal_type: "single_seal_hanger"
            },
            {
                name: "Production Tubing",
                tubular_type: "tubing",
                top_depth: 0,
                bottom_depth: 1000,
                inner_diameter: 3.958,
                outer_diameter: 4.5,
                draw_shoe: false,
                hanger_seal_type: "single_seal_hanger",
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
                uniform_spacing: 0.2
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
                hanger_seal_type: "single_seal_hanger"
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
                hanger_seal_type: "double_seal_hanger",
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
                hanger_seal_type: "double_seal_hanger",
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
                hanger_seal_type: "single_seal_hanger",
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
                figure_size: [6, 10]
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
                hanger_seal_type: "single_seal_hanger"
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
                hanger_seal_type: "double_seal_hanger",
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
                hanger_seal_type: "double_seal_hanger",
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
                hanger_seal_type: "double_seal_hanger",
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
                hanger_seal_type: "single_seal_hanger",
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
            select.options.length = 1;
            
            data.forEach(well => {
                select.options[select.options.length] = new Option(well, well);
            });
        }
    });
}

// =============================================================================
// SCHEMATIC MANAGEMENT
// =============================================================================

/**
 * Checks for saved schematics when well selection changes
 */
function checkForSavedSchematics() {
    const well_name = $('#select_well').val();
    
    if (!well_name) {
        hideAllSchematicUI();
        return;
    }
    
    $('#well_schematics_input_card').hide();
    
    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/get_saved_schematics',
        contentType: 'application/json',
        data: JSON.stringify({ selected_well: well_name }),
        success: function (data) {
            const $select = $('#saved_schematics_select');
            $select.empty();
            
            if (data.length > 0) {
                $select.append('<option value=""></option>');
                data.forEach(schematic => {
                    $select.append(`<option value="${schematic.filename}">${schematic.name}</option>`);
                });
            } else {
                $select.append('<option value="">No saved schematics found</option>');
            }
            // Hide load button since dropdown is reset to empty
            $('#load_schematic_btn').hide();
            $('#saved_schematics_section').show();
        },
        error: function (xhr) {
            console.error('Error loading saved schematics:', xhr);
            $('#saved_schematics_section').hide();
        }
    });
}

/**
 * Loads selected schematic and populates form
 */
function loadSelectedSchematic() {
    const well_name = $('#select_well').val();
    const schematic_filename = $('#saved_schematics_select').val();
    
    if (!well_name || !schematic_filename) {
        showErrorMessage('Please select a well and a schematic');
        return;
    }
    
    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/load_schematic',
        contentType: 'application/json',
        data: JSON.stringify({ 
            selected_well: well_name,
            schematic_filename: schematic_filename
        }),
        success: function (data) {
            // Prioritize API format if both formats exist (new saves include both)
            if (data.well && data.tubulars) {
                // Already in API format - use it directly
                schematicData = JSON.parse(JSON.stringify(data)); // Deep clone
                // Ensure well name matches current selection
                schematicData.well.name = $('#select_well').val() || data.well.name || 'Well';
                
                // Populate wellhead and xmas tree forms
                if (schematicData.well.wellhead_valves) {
                    populateWellheadValvesForm(schematicData.well.wellhead_valves);
                }
                if (schematicData.well.xmas_tree) {
                    populateXmasTreeForm(schematicData.well.xmas_tree);
                }
            } else if (data.units) {
                // Old format only - convert to API format
                const wellName = $('#select_well').val() || 'Well';
                schematicData = {
                    well: {
                        name: wellName,
                        layout: {
                            mode: "uniform",
                            uniform_width: 0.1,
                            uniform_spacing: 0.2
                        }
                    },
                    tubulars: convertOldFormatToApiFormat(data.units, wellName)
                };
            } else {
                // Empty schematic or unknown format
                const wellName = $('#select_well').val() || 'Well';
                schematicData = {
                    well: {
                        name: wellName,
                        layout: {
                            mode: "uniform",
                            uniform_width: 0.1,
                            uniform_spacing: 0.2
                        }
                    },
                    tubulars: []
                };
            }

            if (schematicData.well.layout) {
                populateLayoutForm(schematicData.well.layout);
            }

            if (schematicData.tubulars.length > 0) {
                populateFormFromUnits();
                showSchematicUI();
                showSuccessMessage('Schematic loaded successfully!');
            } else {
                showSchematicUI();
                showSuccessMessage('Schematic loaded but no units found. You can add new units.');
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error ? 
                `Error loading schematic: ${xhr.responseJSON.error}` : 
                'Error loading schematic';
            showErrorMessage(errorMsg);
        }
    });
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
        if (unit.hanger_seal_type) {
            tubular.hanger_seal_type = unit.hanger_seal_type;
        }
        
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
    showUnitManagementButtons();
    
    if (schematicData.tubulars.length > 0) {
        currentUnitIndex = 0;
        updateUnitListDisplay();
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
        const firstSegment = tubular.segments[0];
        const lastSegment = tubular.segments[tubular.segments.length - 1];
        $('#unit_top').val(firstSegment.top_depth);
        $('#unit_bottom').val(lastSegment.bottom_depth);
        $('#unit_id').val(firstSegment.inner_diameter);
        $('#unit_od').val(firstSegment.outer_diameter);
        if (tubular.segments.length === 2) {
            $('#transition_depth').val(tubular.segments[0].bottom_depth);
            $('#bottom_id').val(tubular.segments[1].inner_diameter);
            $('#bottom_od').val(tubular.segments[1].outer_diameter);
        }
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
    
    // Populate draw_shoe and hanger_seal_type
    $('#draw_shoe').prop('checked', tubular.draw_shoe !== false); // Default to true if not specified
    $('#hanger_seal_type').val(tubular.hanger_seal_type || 'double_seal_hanger');
    
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
 * Shows template selection modal
 */
function showTemplateSelection() {
    const schematicName = $('#schematic_name_input').val().trim();
    
    if (!schematicName) {
        showErrorMessage('Please enter a schematic name before creating a new schematic');
        return;
    }
    
    // Show template selection modal
    $('#template_selection_modal').show();
    
    // Reset template card selections
    $('.template-card').removeClass('selected');
}

/**
 * Loads a template and initializes the schematic
 */
function loadTemplate(templateType) {
    const wellName = $('#select_well').val() || 'Well';
    const schematicName = $('#schematic_name_input').val().trim();
    
    // Get the appropriate template
    let template;
    switch(templateType) {
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
    
    // Load template data
    schematicData = JSON.parse(JSON.stringify(template)); // Deep clone
    schematicData.well.name = wellName;
    
    // Hide modal
    $('#template_selection_modal').hide();
    
    // Reset UI and populate form
    resetUI();
    populateFormFromUnits();
    if (schematicData.well.layout) {
        populateLayoutForm(schematicData.well.layout);
    }
    showSchematicUI();

    showSuccessMessage(`Template "${templateType}" loaded successfully!`);
}

/**
 * Creates new schematic from scratch (no template)
 */
function createFromScratch() {
    const wellName = $('#select_well').val() || 'Well';
    
    // Hide modal
    $('#template_selection_modal').hide();
    
    // Reset to empty schematic
    resetAllData();
    schematicData.well.name = wellName;
    resetUI();
    populateLayoutForm(schematicData.well.layout);
    showSchematicUI();

    showSuccessMessage('Ready to create new schematic from scratch!');
}

/**
 * Creates new schematic and clears form (shows template selection)
 */
function createNewSchematic() {
    showTemplateSelection();
}

/**
 * Saves current schematic to server
 * Ensures all current form data is saved before saving the schematic
 */
function saveCurrentSchematic() {
    const well_name = $('#select_well').val();
    const schematic_name = $('#schematic_name_input').val();
    
    if (!well_name) {
        showErrorMessage('Please select a well first');
        return;
    }
    
    if (!schematic_name) {
        showErrorMessage('Please enter a schematic name');
        return;
    }
    
    // If user is currently editing a unit, save those changes first
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = buildUnitDataFromForm();
        schematicData.tubulars[currentUnitIndex] = tubular;
        console.log('Saved current unit changes before saving schematic');
    }
    // If user is in creation mode, add the current unit first
    else if (currentMode === 'creation') {
        const unitName = $('#unit_name').val();
        const unitType = $('#unit_type').val();
        
        if (unitName && unitType) {
            // Validate required fields
            const unitTop = $('#unit_top').val();
            const unitBottom = $('#unit_bottom').val();
            
            if (!unitTop || !unitBottom) {
                showErrorMessage('Please complete the current unit (top and bottom depth) before saving schematic');
                return;
            }
            
            // Build and add the unit
            const tubular = buildUnitDataFromForm();
            schematicData.tubulars.push(tubular);
            console.log('Added current unit before saving schematic');
            
            // Reset creation mode
            currentMode = 'none';
            currentUnitIndex = -1;
            resetTempArrays();
            clearFormFields();
            updateUnitListDisplay();
        }
    }
    
    if (schematicData.tubulars.length === 0) {
        showErrorMessage('Please add at least one unit before saving');
        return;
    }

    // Update well name in schematic data
    schematicData.well.name = well_name;

    // Update layout, wellhead and xmas tree configuration from form
    schematicData.well.layout = buildLayoutConfig();
    schematicData.well.wellhead_valves = buildWellheadValvesConfig();
    schematicData.well.xmas_tree = buildXmasTreeConfig();

    // Deep clone the full schematic data to ensure all nested objects are included
    // Save in API format to preserve all data (well, layout, tubulars with all fields)
    const dataToSave = JSON.parse(JSON.stringify(schematicData));
    
    // Also include units key for backward compatibility
    dataToSave.units = JSON.parse(JSON.stringify(schematicData.tubulars));
    
    console.log('Saving schematic data:', dataToSave);
    console.log('Full schematicData:', schematicData);
    
    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/save_schematic',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_name: schematic_name,
            schematic_data: dataToSave
        }),
        success: function (data) {
            showSuccessMessage('Schematic saved successfully!');
            $('#json_input_error').text('');
            $('#schematic_name_input').val('');
            $('#new_schematic_btn').prop('disabled', true);
            checkForSavedSchematics();
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error ? 
                `Error saving schematic: ${xhr.responseJSON.error}` : 
                'Error saving schematic';
            $('#json_input_error').text(errorMsg);
            $('#save_success_message').text('');
        }
    });
}

/**
 * Saves the current schematic data to the server
 */
function saveSchematicToServer(schematicFilename) {
    const well_name = $('#select_well').val();
    const schematic_name = schematicFilename.replace('.json', ''); // Remove .json extension
    
    // Update well name in schematic data
    schematicData.well.name = well_name;

    // Update layout, wellhead and xmas tree configuration from form
    schematicData.well.layout = buildLayoutConfig();
    schematicData.well.wellhead_valves = buildWellheadValvesConfig();
    schematicData.well.xmas_tree = buildXmasTreeConfig();

    // Deep clone the full schematic data to ensure all nested objects are included
    // Save in API format to preserve all data (well, layout, tubulars with all fields)
    const dataToSave = JSON.parse(JSON.stringify(schematicData));

    // Also include units key for backward compatibility
    dataToSave.units = JSON.parse(JSON.stringify(schematicData.tubulars));

    console.log('Auto-saving schematic to server:', schematic_name);
    console.log('Schematic data:', dataToSave);
    
    $.ajax({
        type: 'POST',
        url: '/app/well_schematics/save_schematic',
        contentType: 'application/json',
        data: JSON.stringify({
            selected_well: well_name,
            schematic_name: schematic_name,
            schematic_data: dataToSave
        }),
        success: function (data) {
            console.log('Schematic auto-saved successfully:', data);
            showSuccessMessage('Changes saved successfully!');
        },
        error: function (xhr) {
            console.error('Failed to auto-save schematic:', xhr.responseJSON?.error || 'Unknown error');
            $('#json_input_error').text('Failed to save changes. Please try saving manually.');
        }
    });
}

/**
 * Builds tubular data from form fields in API format
 */
function buildUnitDataFromForm() {
    const tubularType = $('#unit_type').val();
    const isTapered = tubularType === 'casing' && $('#is_tapered').is(':checked');
    
    const tubular = {
        name: $('#unit_name').val(),
        tubular_type: isTapered ? 'tapered_casing' : tubularType
    };
    
    // Handle tapered casing
    if (isTapered) {
        const topDepth = parseFloat($('#unit_top').val()) || 0;
        const bottomDepth = parseFloat($('#unit_bottom').val()) || 1500;
        const transitionDepth = parseFloat($('#transition_depth').val());
        const topID = parseFloat($('#unit_id').val()) || 10;
        const topOD = parseFloat($('#unit_od').val()) || 12;
        const bottomID = parseFloat($('#bottom_id').val()) || 10;
        const bottomOD = parseFloat($('#bottom_od').val()) || 12;
        
        tubular.segments = [
            {
                top_depth: topDepth,
                bottom_depth: transitionDepth,
                inner_diameter: topID,
                outer_diameter: topOD
            },
            {
                top_depth: transitionDepth,
                bottom_depth: bottomDepth,
                inner_diameter: bottomID,
                outer_diameter: bottomOD
            }
        ];
    } else {
        tubular.top_depth = parseFloat($('#unit_top').val()) || 0;
        tubular.bottom_depth = parseFloat($('#unit_bottom').val()) || 1500;
        tubular.inner_diameter = parseFloat($('#unit_id').val()) || 10;
        tubular.outer_diameter = parseFloat($('#unit_od').val()) || 12;
    }
    
    if ($('#unit_oh').val() !== '') {
        tubular.openhole_diameter = parseFloat($('#unit_oh').val());
    }
    
    if ($('#hole_top_depth').val() !== '') {
        tubular.hole_top_depth = parseFloat($('#hole_top_depth').val());
    }
    
    if ($('#hole_bottom_depth').val() !== '') {
        tubular.hole_bottom_depth = parseFloat($('#hole_bottom_depth').val());
    }
    
    // Add draw_shoe and hanger_seal_type
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
    
    // ESP (only for tubing)
    if (tubular.tubular_type === 'tubing' && $('#esp_enabled').is(':checked')) {
        const espTop = parseFloat($('#esp_top_depth').val());
        const espBottom = parseFloat($('#esp_bottom_depth').val());
        tubular.esp = {
            enabled: true,
            top_depth: isNaN(espTop) ? 0 : espTop,
            bottom_depth: isNaN(espBottom) ? 0 : espBottom
        };
    }
    
    // Build fluids array (with location)
    const fluids = [];
    
    if (currentMode === 'creation') {
        fluids.push(...tempFluids);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0) {
        const currentTubular = schematicData.tubulars[currentUnitIndex];
        fluids.push(...(currentTubular.fluids || []));
    }
    
    if (fluids.length > 0) {
        tubular.fluids = fluids;
    }
    
    // Build cements array
    let cements = [];
    if (currentMode === 'creation') {
        cements.push(...tempCements);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0) {
        const currentTubular = schematicData.tubulars[currentUnitIndex];
        cements.push(...(currentTubular.cements || []));
    }
    if (cements.length > 0) {
        tubular.cements = cements;
    }
    
    // Build packers array
    let packers = [];
    if (currentMode === 'creation') {
        packers = tempPackers.map(p => ({
            packer_type: p.packer_type,
            top_depth: p.depth_interval?.top || p.top_depth,
            bottom_depth: p.depth_interval?.bottom || p.bottom_depth
        }));
    } else if (currentMode === 'editing' && currentUnitIndex >= 0) {
        const currentTubular = schematicData.tubulars[currentUnitIndex];
        packers = [...(currentTubular.packers || [])];
    }
    if (packers.length > 0) {
        tubular.packers = packers;
    }
    
    // Build plugs array
    let plugs = [];
    if (currentMode === 'creation') {
        plugs = tempPlugs.map(p => ({
            plug_type: p.type || p.plug_type, // Use type field as plug_type
            top_depth: p.depth_interval?.top || p.top_depth,
            bottom_depth: p.depth_interval?.bottom || p.bottom_depth
        }));
    } else if (currentMode === 'editing' && currentUnitIndex >= 0) {
        const currentTubular = schematicData.tubulars[currentUnitIndex];
        plugs = [...(currentTubular.plugs || [])];
    }
    if (plugs.length > 0) {
        tubular.plugs = plugs;
    }
    
    // Build screens array
    let screens = [];
    if (currentMode === 'creation') {
        screens.push(...tempScreens);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0) {
        const currentTubular = schematicData.tubulars[currentUnitIndex];
        screens.push(...(currentTubular.screens || []));
    }
    if (screens.length > 0) {
        tubular.screens = screens;
    }
    
    return tubular;
}

/**
 * Populates sub-elements from tubular data (API format)
 */
function populateSubElements(tubular) {
    console.log('Populating sub-elements for tubular:', tubular);
    
    // Get fluids (already in API format with location)
    const fluidsLocal = tubular.fluids || [];
    
    // Get cements (already in API format with location)
    const cementsLocal = tubular.cements || [];
    
    // Get packers (convert from API format to display format)
    const packersLocal = (tubular.packers || []).map(p => ({
        packer_type: p.packer_type,
        top_depth: p.top_depth,
        bottom_depth: p.bottom_depth
    }));
    
    // Get plugs (convert from API format to display format)
    const plugsLocal = (tubular.plugs || []).map(p => ({
        plug_type: p.plug_type, // The actual plug type (cement/bridge/mechanical)
        top_depth: p.top_depth,
        bottom_depth: p.bottom_depth
    }));
    
    // Get screens (already in API format)
    const screensLocal = tubular.screens || [];
    
    const perfsLocal = []; // Perforations not in API format yet

    // Helper for selected row style
    const selStyle = (type, i) => (currentMode === 'editing' && selectedSubType === type && selectedSubIndex === i)
        ? 'padding: 5px; margin: 2px 0; background: #e7f1ff; border-radius: 3px; border-left: 3px solid #007bff; display: flex; justify-content: space-between; align-items: center; cursor: pointer;'
        : 'padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center; cursor: pointer;';

    // Update fluids display (combined)
    if (fluidsLocal.length > 0) {
        $('#fluids_list').html(fluidsLocal.map((f, i) =>
            `<div style="${selStyle('fluid', i)}" onclick="selectFluid(${i})" title="Click to select and edit">
                <span>${i+1}. ${f.fluid_type} (${f.location}) (${f.top_depth}-${f.bottom_depth})</span>
                ${currentMode === 'editing' ? `<button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removeFluid(${i});" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>` : ''}
            </div>`
        ).join(''));
    } else {
        $('#fluids_list').html('<div style="color: #666; font-style: italic; text-align: center;">No fluids added yet</div>');
    }
    
    // Update cements display
    if (cementsLocal.length > 0) {
        $('#cements_list').html(cementsLocal.map((c, i) =>
            `<div style="${selStyle('cement', i)}" onclick="selectCement(${i})" title="Click to select and edit">
                <span>${i+1}. ${c.cement_type} (${c.location}) (${c.top_depth}-${c.bottom_depth})</span>
                ${currentMode === 'editing' ? `<button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removeCement(${i});" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>` : ''}
            </div>`
        ).join(''));
    } else {
        $('#cements_list').html('<div style="color: #666; font-style: italic; text-align: center;">No cements added yet</div>');
    }
    
    if (packersLocal.length > 0) {
        $('#packers_list').html(packersLocal.map((p, i) =>
            `<div style="${selStyle('packer', i)}" onclick="selectPacker(${i})" title="Click to select and edit">
                <span>${i+1}. ${p.packer_type} (${p.top_depth}-${p.bottom_depth})</span>
                ${currentMode === 'editing' ? `<button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removePacker(${i});" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>` : ''}
            </div>`
        ).join(''));
    } else {
        $('#packers_list').html('<div style="color: #666; font-style: italic; text-align: center;">No packers added yet</div>');
    }
    
    if (plugsLocal.length > 0) {
        $('#plugs_list').html(plugsLocal.map((p, i) =>
            `<div style="${selStyle('plug', i)}" onclick="selectPlug(${i})" title="Click to select and edit">
                <span>${i+1}. ${p.plug_type} (${p.top_depth}-${p.bottom_depth})</span>
                ${currentMode === 'editing' ? `<button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removePlug(${i});" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>` : ''}
            </div>`
        ).join(''));
    } else {
        $('#plugs_list').html('<div style="color: #666; font-style: italic; text-align: center;">No plugs added yet</div>');
    }
    
    // Update screens display
    if (screensLocal.length > 0) {
        $('#screens_list').html(screensLocal.map((s, i) =>
            `<div style="${selStyle('screen', i)}" onclick="selectScreen(${i})" title="Click to select and edit">
                <span>${i+1}. ${s.screen_type} (${s.top_depth}-${s.bottom_depth})</span>
                ${currentMode === 'editing' ? `<button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removeScreen(${i});" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>` : ''}
            </div>`
        ).join(''));
    } else {
        $('#screens_list').html('<div style="color: #666; font-style: italic; text-align: center;">No screens added yet</div>');
    }
    
    if (perfsLocal.length > 0) {
        $('#perfs_list').html(perfsLocal.map((p, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. (${p.depth_interval.top}-${p.depth_interval.bottom}) Phases: ${p.phases}, Density: ${p.density}</span>
                ${currentMode === 'editing' ? `<button class="btn btn-sm btn-danger" onclick="removePerforation(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>` : ''}
            </div>`
        ).join(''));
    } else {
        $('#perfs_list').html('<div style="color: #666; font-style: italic; text-align: center;">No perforations added yet</div>');
    }

    // In editing mode, show/hide update buttons based on selection
    if (currentMode === 'editing') {
        $('#update_fluid_btn').toggle(selectedSubType === 'fluid' && selectedSubIndex >= 0 && selectedSubIndex < fluidsLocal.length);
        $('#update_cement_btn').toggle(selectedSubType === 'cement' && selectedSubIndex >= 0 && selectedSubIndex < cementsLocal.length);
        $('#update_packer_btn').toggle(selectedSubType === 'packer' && selectedSubIndex >= 0 && selectedSubIndex < packersLocal.length);
        $('#update_plug_btn').toggle(selectedSubType === 'plug' && selectedSubIndex >= 0 && selectedSubIndex < plugsLocal.length);
        $('#update_screen_btn').toggle(selectedSubType === 'screen' && selectedSubIndex >= 0 && selectedSubIndex < screensLocal.length);
    } else {
        $('#update_fluid_btn, #update_cement_btn, #update_packer_btn, #update_plug_btn, #update_screen_btn').hide();
    }

    if (perfsLocal.length > 0) {
        const first = perfsLocal[0];
        $('#perf_top').val(first.depth_interval.top);
        $('#perf_bottom').val(first.depth_interval.bottom);
        $('#perf_phases').val(first.phases);
        $('#perf_density').val(first.density);
    }
}

/**
 * Updates tapered casing fields with calculated values
 */
function updateTaperedFields() {
    const topDepth = parseFloat($('#unit_top').val()) || 0;
    const bottomDepth = parseFloat($('#unit_bottom').val()) || 1000;
    const transitionDepth = topDepth + (bottomDepth - topDepth) * 0.5;
    $('#transition_depth').val(transitionDepth.toFixed(1));
    
    const topID = parseFloat($('#unit_id').val()) || 9.0;
    const topOD = parseFloat($('#unit_od').val()) || 9.625;
    $('#bottom_id').val((topID - 0.5).toFixed(3));
    $('#bottom_od').val((topOD - 0.5).toFixed(3));
}



// =============================================================================
// UNIT MANAGEMENT
// =============================================================================

/**
 * Starts creation of a new unit
 */
function startNewUnitCreation() {
    currentMode = 'creation';
    currentUnitIndex = -1;
    
    // Clear form and temporary arrays
    clearFormFields();
    resetTempArrays();
    
    // Show creation mode UI
    $('#unit_creation_controls').show();
    $('#unit_editing_controls').hide();
    $('#unit_selector_group').hide();
    $('#add_unit_btn').show();
    $('#edit_unit_btn').hide();
    
    // Enable form fields
    enableFormFields();
    
    console.log('Started new unit creation mode');
}

/**
 * Starts editing an existing unit
 */
function startUnitEditing(unitIndex) {
    if (unitIndex < 0 || unitIndex >= schematicData.tubulars.length) {
        console.warn('Invalid unit index for editing:', unitIndex);
        return;
    }
    
    currentMode = 'editing';
    currentUnitIndex = unitIndex;
    clearSubSelection();
    
    // Populate form with unit data
    populateFormWithUnit(unitIndex);
    
    // Show editing mode UI
    $('#unit_editing_controls').show();
    $('#unit_creation_controls').hide();
    $('#unit_selector_group').hide();
    $('#add_unit_btn').hide();
    $('#edit_unit_btn').hide();
    
    // Enable form fields
    enableFormFields();
    
    console.log('Started editing unit:', unitIndex);
}

/**
 * Cancels current editing mode
 */
function cancelUnitEditing() {
    currentMode = 'none';
    currentUnitIndex = -1;
    clearSubSelection();

    disableFormFields();
    
    // Clear form
    clearFormFields();
    resetTempArrays();
    
    // Hide all mode-specific UI
    $('#unit_editing_controls').hide();
    $('#unit_creation_controls').hide();
    $('#add_unit_btn').hide();
    
    // Show unit list and management buttons
    updateUnitListDisplay();
    showUnitManagementButtons();
    
    console.log('Cancelled unit editing');
}

/**
 * Saves current unit (either new or edited)
 */
function saveCurrentUnit() {
    if (currentMode === 'creation') {
        addNewUnit();
    } else if (currentMode === 'editing') {
        saveUnitChanges();
    }
}

/**
 * Adds a new unit from form data
 */
function addNewUnit() {
    // Validate basic unit data
    const unitName = $('#unit_name').val().trim();
    const unitType = $('#unit_type').val();
    
    if (!unitName || !unitType) {
        showErrorMessage('Please provide a unit name and type');
        return;
    }
    
    // Build tubular data from form (in API format)
    const tubular = buildUnitDataFromForm();
    
    // Add to tubulars array
    schematicData.tubulars.push(tubular);
    
    // Reset to normal mode
    currentMode = 'none';
    currentUnitIndex = -1;
    
    // Update UI
    updateUnitListDisplay();
    showUnitManagementButtons();
    clearFormFields();
    resetTempArrays();
    
    // Hide mode-specific UI
    $('#unit_creation_controls').hide();
    $('#add_unit_btn').hide();
    
    showSuccessMessage('Unit added successfully!');
    console.log('Added new unit:', unitData);
}

/**
 * Saves changes to current unit
 */
function saveUnitChanges() {
    if (currentUnitIndex < 0 || currentUnitIndex >= schematicData.tubulars.length) {
        console.warn('Invalid unit index for saving:', currentUnitIndex);
        return;
    }
    
    // Build tubular data from form (in API format)
    const tubular = buildUnitDataFromForm();
    
    // Update tubulars array
    schematicData.tubulars[currentUnitIndex] = tubular;
    
    // Save schematic to server if we have a loaded schematic
    const loadedSchematicName = $('#saved_schematics_select').val();
    if (loadedSchematicName) {
        saveSchematicToServer(loadedSchematicName);
    }
    
    // Reset to normal mode
    currentMode = 'none';
    currentUnitIndex = -1;
    
    // Update UI
    updateUnitListDisplay();
    showUnitManagementButtons();
    clearFormFields();
    resetTempArrays();
    
    // Hide mode-specific UI
    $('#unit_editing_controls').hide();
    
    showSuccessMessage('Unit updated and schematic saved successfully!');
    console.log('Updated unit:', unitData);
}

/**
 * Deletes current unit
 */
function deleteCurrentUnit() {
    if (currentUnitIndex < 0 || currentUnitIndex >= schematicData.tubulars.length) {
        showErrorMessage('No unit selected to delete');
        return;
    }
    
    if (!confirm('Are you sure you want to delete this unit?')) {
        return;
    }
    
    // Remove from array
    schematicData.tubulars.splice(currentUnitIndex, 1);
    
    // Reset to normal mode
    currentMode = 'none';
    currentUnitIndex = -1;
    
    // Update UI
    updateUnitListDisplay();
    showUnitManagementButtons();
    clearFormFields();
    resetTempArrays();
    
    // Hide mode-specific UI
    $('#unit_editing_controls').hide();
    
    showSuccessMessage('Unit deleted successfully!');
    console.log('Deleted unit at index:', currentUnitIndex);
}

/**
 * Updates unit list display with better formatting and click handling
 */
function updateUnitListDisplay() {
    const $unitList = $('#unit_list');
    
    if (schematicData.tubulars.length === 0) {
        $unitList.html(`
            <div style="color: #666; font-style: italic; text-align: center; padding: 20px;">
                No units defined yet. Start by adding your first unit below.
            </div>
        `);
        return;
    }
    
    const html = schematicData.tubulars.map((tubular, index) => {
        const isSelected = index === currentUnitIndex;
        const selectedClass = isSelected ? 'border-primary' : '';
        const selectedStyle = isSelected ? 'background-color: #e3f2fd;' : '';
        
        // Get depth info
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
        
        let displayText = `
            <div class="unit-item" data-unit-index="${index}" style="padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 5px; cursor: pointer; ${selectedStyle}" class="${selectedClass}">
                <div style="font-weight: bold; color: #007bff;">${tubular.name}</div>
                <div style="font-size: 0.9em; color: #666;">
                    <span class="badge badge-secondary">${tubular.tubular_type}</span>
                    <span style="margin-left: 10px;">${topDepth} - ${bottomDepth} m</span>
                </div>
                <div style="font-size: 0.8em; color: #888; margin-top: 5px;">
                    ID: ${innerDiameter}" | OD: ${outerDiameter}"
                    ${isTapered ? ' | 🔸 Tapered' : ''}
                </div>
                <div style="font-size: 0.8em; color: #888;">
                    Fluids: ${fluidCount} | 
                    Cements: ${cementCount} | 
                    Packers: ${tubular.packers?.length || 0} | 
                    Plugs: ${tubular.plugs?.length || 0} | 
                    Screens: ${tubular.screens?.length || 0}
                </div>
            </div>
        `;
        return displayText;
    }).join('');
    
    $unitList.html(html);
    
    // Add click handlers to unit items
    $('.unit-item').off('click').on('click', function() {
        const unitIndex = parseInt($(this).data('unit-index'));
        if (currentMode === 'none') {
            selectUnitFromList(unitIndex);
            // Show edit button when a unit is selected
            $('#edit_unit_btn').show();
        }
    });
}

/**
 * Selects a unit from the list
 */
function selectUnitFromList(unitIndex) {
    if (unitIndex < 0 || unitIndex >= schematicData.tubulars.length) {
        console.warn('Invalid unit index:', unitIndex);
        return;
    }
    
    currentUnitIndex = unitIndex;
    // Just update the display to show selection, don't enter edit mode yet
    updateUnitListDisplay();
    console.log('Selected unit from list:', unitIndex);
}

/**
 * Shows unit management buttons based on current state
 */
function showUnitManagementButtons() {
    // Only show edit button if a unit is selected
    $('#edit_unit_btn').toggle(currentUnitIndex >= 0);
}

/**
 * Enables form fields for editing
 */
function enableFormFields() {
    $('#unit_type, #unit_name, #unit_top, #unit_bottom, #unit_id, #unit_od, #unit_oh, #hole_top_depth, #hole_bottom_depth, #draw_shoe, #hanger_seal_type, #esp_enabled, #esp_top_depth, #esp_bottom_depth, #fluid_type, #fluid_location, #fluid_top, #fluid_bottom, #add_fluid_btn, #cement_type, #cement_location, #cement_top, #cement_bottom, #add_cement_btn, #packer_type, #packer_top, #packer_bottom, #add_packer_btn, #plug_plugtype, #plug_top, #plug_bottom, #add_plug_btn, #screen_type, #screen_top, #screen_bottom, #add_screen_btn').prop('disabled', false);
    $('#is_tapered, #transition_depth, #bottom_id, #bottom_od').prop('disabled', false);
}

/**
 * Disables form fields
 */
function disableFormFields() {
    $('#unit_type, #unit_name, #unit_top, #unit_bottom, #unit_id, #unit_od, #unit_oh, #hole_top_depth, #hole_bottom_depth, #draw_shoe, #hanger_seal_type, #esp_enabled, #esp_top_depth, #esp_bottom_depth, #fluid_type, #fluid_location, #fluid_top, #fluid_bottom, #add_fluid_btn, #cement_type, #cement_location, #cement_top, #cement_bottom, #add_cement_btn, #packer_type, #packer_top, #packer_bottom, #add_packer_btn, #plug_plugtype, #plug_top, #plug_bottom, #add_plug_btn, #screen_type, #screen_top, #screen_bottom, #add_screen_btn').prop('disabled', true);
    $('#is_tapered, #transition_depth, #bottom_id, #bottom_od').prop('disabled', true);
}

/**
 * Resets temporary arrays for sub-elements
 */
function resetTempArrays() {
    tempFluids = [];
    tempCements = [];
    tempPackers = [];
    tempPlugs = [];
    tempScreens = [];
    tempPerforations = [];
    updateTempSubElementDisplays();
}

/**
 * Updates displays for temporary sub-elements
 */
function updateTempSubElementDisplays() {
    // Update fluids display (combined)
    if (tempFluids.length > 0) {
        $('#fluids_list').html(tempFluids.map((f, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. ${f.fluid_type} (${f.location}) (${f.top_depth}-${f.bottom_depth})</span>
                <button class="btn btn-sm btn-danger" onclick="removeTempFluid(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>`
        ).join(''));
    } else {
        $('#fluids_list').html('<div style="color: #666; font-style: italic; text-align: center;">No fluids added yet</div>');
    }
    
    // Update cements display
    if (tempCements.length > 0) {
        $('#cements_list').html(tempCements.map((c, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. ${c.cement_type} (${c.location}) (${c.top_depth}-${c.bottom_depth})</span>
                <button class="btn btn-sm btn-danger" onclick="removeTempCement(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>`
        ).join(''));
    } else {
        $('#cements_list').html('<div style="color: #666; font-style: italic; text-align: center;">No cements added yet</div>');
    }
    
    // Update packers display
    if (tempPackers.length > 0) {
        $('#packers_list').html(tempPackers.map((p, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. ${p.packer_type} (${p.top_depth || p.depth_interval?.top}-${p.bottom_depth || p.depth_interval?.bottom})</span>
                <button class="btn btn-sm btn-danger" onclick="removeTempPacker(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>`
        ).join(''));
    } else {
        $('#packers_list').html('<div style="color: #666; font-style: italic; text-align: center;">No packers added yet</div>');
    }
    
    // Update plugs display
    if (tempPlugs.length > 0) {
        $('#plugs_list').html(tempPlugs.map((p, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. ${p.plug_type || p.type} (${p.top_depth || p.depth_interval?.top}-${p.bottom_depth || p.depth_interval?.bottom})</span>
                <button class="btn btn-sm btn-danger" onclick="removeTempPlug(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>`
        ).join(''));
    } else {
        $('#plugs_list').html('<div style="color: #666; font-style: italic; text-align: center;">No plugs added yet</div>');
    }
    
    // Update screens display
    if (tempScreens.length > 0) {
        $('#screens_list').html(tempScreens.map((s, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. ${s.screen_type} (${s.top_depth}-${s.bottom_depth})</span>
                <button class="btn btn-sm btn-danger" onclick="removeTempScreen(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>`
        ).join(''));
    } else {
        $('#screens_list').html('<div style="color: #666; font-style: italic; text-align: center;">No screens added yet</div>');
    }
    
    // Update perforations display
    if (tempPerforations.length > 0) {
        $('#perfs_list').html(tempPerforations.map((p, i) =>
            `<div style="padding: 5px; margin: 2px 0; background: white; border-radius: 3px; display: flex; justify-content: space-between; align-items: center;">
                <span>${i+1}. (${p.depth_interval.top}-${p.depth_interval.bottom}) Phases: ${p.phases}, Density: ${p.density}</span>
                <button class="btn btn-sm btn-danger" onclick="removeTempPerforation(${i})" style="padding: 4px 8px;">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>`
        ).join(''));
    } else {
        $('#perfs_list').html('<div style="color: #666; font-style: italic; text-align: center;">No perforations added yet</div>');
    }
}

// =============================================================================
// UNIT MANAGEMENT
// =============================================================================

/**
 * Saves current form data to wellUnits array
 */
function saveCurrentFormData() {
    if (currentUnitIndex < 0 || currentUnitIndex >= schematicData.tubulars.length) {
        console.warn('Invalid unit index:', currentUnitIndex, 'Total units:', schematicData.tubulars.length);
        return false;
    }
    
    // Validate that we have basic unit data
    const unitName = $('#unit_name').val();
    const unitType = $('#unit_type').val();
    
    if (!unitName || !unitType) {
        console.warn('Missing required unit data - name:', unitName, 'type:', unitType);
        return false;
    }
    
    // Build the tubular data from form fields (in API format)
    const tubular = buildUnitDataFromForm();
    
    // Update the tubular in the array
    schematicData.tubulars[currentUnitIndex] = tubular;
    
    console.log('Saved tubular data:', tubular);
    console.log('Updated schematicData:', schematicData);
    
    updateUnitListDisplay();
    
    // If we have a loaded schematic, also save it to the server
    const loadedSchematicName = $('#saved_schematics_select').val();
    if (loadedSchematicName) {
        saveSchematicToServer(loadedSchematicName);
    }
    
    return true;
}

// =============================================================================
// SUB-ELEMENT MANAGEMENT
// =============================================================================

/**
 * Adds fluid to current unit or temporary array (with location)
 */
function addFluid() {
    const fluid = {
        fluid_type: $('#fluid_type').val(),
        location: $('#fluid_location').val(),
        top_depth: parseFloat($('#fluid_top').val()),
        bottom_depth: parseFloat($('#fluid_bottom').val())
    };
    
    // Validate fluid data
    if (!fluid.fluid_type || !fluid.location || isNaN(fluid.top_depth) || isNaN(fluid.bottom_depth)) {
        showErrorMessage('Please fill in all fluid fields');
        return;
    }
    
    if (currentMode === 'creation') {
        // Add to temporary array
        tempFluids.push(fluid);
        updateTempSubElementDisplays();
        clearFluidFields();
        console.log('Added fluid to temp array:', fluid);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        // Add to current tubular
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (!tubular.fluids) {
            tubular.fluids = [];
        }
        tubular.fluids.push(fluid);
        // Preserve draw_shoe and hanger_seal_type from form
        tubular.draw_shoe = $('#draw_shoe').is(':checked');
        tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
        
        // Update displays without saving to server
        populateSubElements(tubular);
        clearFluidFields();
        
        showSuccessMessage('Fluid added! Click "Save Changes" to persist.');
        console.log('Added fluid to unit:', currentUnitIndex, fluid);
    } else {
        showErrorMessage('Please start creating or editing a unit first.');
    }
}

/**
 * Adds cement to current unit or temporary array (API format)
 */
function addCement() {
    const cement = {
        cement_type: $('#cement_type').val(),
        location: $('#cement_location').val(),
        top_depth: parseFloat($('#cement_top').val()),
        bottom_depth: parseFloat($('#cement_bottom').val())
    };
    
    // Validate cement data
    if (!cement.cement_type || !cement.location || isNaN(cement.top_depth) || isNaN(cement.bottom_depth)) {
        showErrorMessage('Please fill in all cement fields');
        return;
    }
    
    if (currentMode === 'creation') {
        // Add to temporary array
        tempCements.push(cement);
        updateTempSubElementDisplays();
        clearCementFields();
        console.log('Added cement to temp array:', cement);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        // Add to current tubular
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (!tubular.cements) {
            tubular.cements = [];
        }
        tubular.cements.push(cement);
        // Preserve draw_shoe and hanger_seal_type from form
        tubular.draw_shoe = $('#draw_shoe').is(':checked');
        tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
        
        // Update displays without saving to server
        populateSubElements(tubular);
        clearCementFields();
        
        showSuccessMessage('Cement added! Click "Save Changes" to persist.');
        console.log('Added cement to unit:', currentUnitIndex, cement);
    } else {
        showErrorMessage('Please start creating or editing a unit first.');
    }
}

/**
 * Adds packer to current unit or temporary array (API format)
 */
function addPacker() {
    const packer = {
        packer_type: $('#packer_type').val(),
        top_depth: parseFloat($('#packer_top').val()),
        bottom_depth: parseFloat($('#packer_bottom').val())
    };
    
    // Validate packer data
    if (!packer.packer_type || isNaN(packer.top_depth) || isNaN(packer.bottom_depth)) {
        showErrorMessage('Please fill in all packer fields');
        return;
    }
    
    if (currentMode === 'creation') {
        // Add to temporary array
        tempPackers.push(packer);
        updateTempSubElementDisplays();
        clearPackerFields();
        console.log('Added packer to temp array:', packer);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        // Add to current tubular
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (!tubular.packers) {
            tubular.packers = [];
        }
        tubular.packers.push(packer);
        // Preserve draw_shoe and hanger_seal_type from form
        tubular.draw_shoe = $('#draw_shoe').is(':checked');
        tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
        populateSubElements(tubular);
        console.log('Added packer to unit:', currentUnitIndex, packer);
    } else {
        showErrorMessage('Please start creating or editing a unit first.');
    }
}

/**
 * Adds plug to current unit or temporary array (API format)
 */
function addPlug() {
    const plug = {
        plug_type: $('#plug_plugtype').val(), // Use plug_plugtype as plug_type (cement/bridge/mechanical)
        top_depth: parseFloat($('#plug_top').val()),
        bottom_depth: parseFloat($('#plug_bottom').val())
    };
    
    // Validate plug data
    if (!plug.plug_type || isNaN(plug.top_depth) || isNaN(plug.bottom_depth)) {
        showErrorMessage('Please fill in all plug fields');
        return;
    }
    
    if (currentMode === 'creation') {
        // Add to temporary array
        tempPlugs.push(plug);
        updateTempSubElementDisplays();
        clearPlugFields();
        console.log('Added plug to temp array:', plug);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        // Add to current tubular
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (!tubular.plugs) {
            tubular.plugs = [];
        }
        tubular.plugs.push(plug);
        // Preserve draw_shoe and hanger_seal_type from form
        tubular.draw_shoe = $('#draw_shoe').is(':checked');
        tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
        populateSubElements(tubular);
        console.log('Added plug to unit:', currentUnitIndex, plug);
    } else {
        showErrorMessage('Please start creating or editing a unit first.');
    }
}

/**
 * Adds screen to current unit or temporary array (API format)
 */
function addScreen() {
    const screen = {
        screen_type: $('#screen_type').val(),
        top_depth: parseFloat($('#screen_top').val()),
        bottom_depth: parseFloat($('#screen_bottom').val())
    };
    
    // Validate screen data
    if (!screen.screen_type || isNaN(screen.top_depth) || isNaN(screen.bottom_depth)) {
        showErrorMessage('Please fill in all screen fields');
        return;
    }
    
    if (currentMode === 'creation') {
        // Add to temporary array
        tempScreens.push(screen);
        updateTempSubElementDisplays();
        clearScreenFields();
        console.log('Added screen to temp array:', screen);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        // Add to current tubular
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (!tubular.screens) {
            tubular.screens = [];
        }
        tubular.screens.push(screen);
        // Preserve draw_shoe and hanger_seal_type from form
        tubular.draw_shoe = $('#draw_shoe').is(':checked');
        tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
        populateSubElements(tubular);
        clearScreenFields();
        showSuccessMessage('Screen added! Click "Save Changes" to persist.');
        console.log('Added screen to unit:', currentUnitIndex, screen);
    } else {
        showErrorMessage('Please start creating or editing a unit first.');
    }
}

/**
 * Adds perforation to current unit or temporary array
 */
function addPerforation() {
    const perf = {
        depth_interval: {
            top: parseFloat($('#perf_top').val()),
            bottom: parseFloat($('#perf_bottom').val())
        },
        phases: parseInt($('#perf_phases').val()),
        density: parseInt($('#perf_density').val())
    };
    
    // Validate perforation data
    if (isNaN(perf.depth_interval.top) || isNaN(perf.depth_interval.bottom) || 
        isNaN(perf.phases) || isNaN(perf.density)) {
        showErrorMessage('Please fill in all perforation fields');
        return;
    }
    
    if (currentMode === 'creation') {
        // Add to temporary array
        tempPerforations.push(perf);
        updateTempSubElementDisplays();
        clearPerfFields();
        console.log('Added perforation to temp array:', perf);
    } else if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < wellUnits.length) {
        // Add to current unit
        if (!wellUnits[currentUnitIndex].perforations) {
            wellUnits[currentUnitIndex].perforations = [];
        }
        wellUnits[currentUnitIndex].perforations.push(perf);
        populateSubElements(wellUnits[currentUnitIndex]);
        console.log('Added perforation to unit:', currentUnitIndex, perf);
    } else {
        showErrorMessage('Please start creating or editing a unit first.');
    }
}

// Temporary array removal functions
function removeTempFluid(index) {
    tempFluids.splice(index, 1);
    updateTempSubElementDisplays();
}

function removeTempCement(index) {
    tempCements.splice(index, 1);
    updateTempSubElementDisplays();
}

function removeTempPacker(index) {
    tempPackers.splice(index, 1);
    updateTempSubElementDisplays();
}

function removeTempPlug(index) {
    tempPlugs.splice(index, 1);
    updateTempSubElementDisplays();
}

function removeTempScreen(index) {
    tempScreens.splice(index, 1);
    updateTempSubElementDisplays();
}

function removeTempPerforation(index) {
    tempPerforations.splice(index, 1);
    updateTempSubElementDisplays();
}

// Editing mode removal functions
function removeFluid(index) {
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (tubular.fluids && tubular.fluids.length > index) {
            tubular.fluids.splice(index, 1);
            if (selectedSubType === 'fluid') { if (selectedSubIndex === index) clearSubSelection(); else if (selectedSubIndex > index) selectedSubIndex--; }
            tubular.draw_shoe = $('#draw_shoe').is(':checked');
            tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
            populateSubElements(tubular);
            showSuccessMessage('Fluid removed! Click "Save Changes" to persist.');
        }
    }
}

function removeCement(index) {
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (tubular.cements && tubular.cements.length > index) {
            tubular.cements.splice(index, 1);
            if (selectedSubType === 'cement') { if (selectedSubIndex === index) clearSubSelection(); else if (selectedSubIndex > index) selectedSubIndex--; }
            tubular.draw_shoe = $('#draw_shoe').is(':checked');
            tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
            populateSubElements(tubular);
            showSuccessMessage('Cement removed! Click "Save Changes" to persist.');
        }
    }
}

function removePacker(index) {
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (tubular.packers && tubular.packers.length > index) {
            tubular.packers.splice(index, 1);
            if (selectedSubType === 'packer') { if (selectedSubIndex === index) clearSubSelection(); else if (selectedSubIndex > index) selectedSubIndex--; }
            tubular.draw_shoe = $('#draw_shoe').is(':checked');
            tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
            populateSubElements(tubular);
            showSuccessMessage('Packer removed! Click "Save Changes" to persist.');
        }
    }
}

function removePlug(index) {
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (tubular.plugs && tubular.plugs.length > index) {
            tubular.plugs.splice(index, 1);
            if (selectedSubType === 'plug') { if (selectedSubIndex === index) clearSubSelection(); else if (selectedSubIndex > index) selectedSubIndex--; }
            tubular.draw_shoe = $('#draw_shoe').is(':checked');
            tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
            populateSubElements(tubular);
            showSuccessMessage('Plug removed! Click "Save Changes" to persist.');
        }
    }
}

function removeScreen(index) {
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = schematicData.tubulars[currentUnitIndex];
        if (tubular.screens && tubular.screens.length > index) {
            tubular.screens.splice(index, 1);
            if (selectedSubType === 'screen') { if (selectedSubIndex === index) clearSubSelection(); else if (selectedSubIndex > index) selectedSubIndex--; }
            tubular.draw_shoe = $('#draw_shoe').is(':checked');
            tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
            populateSubElements(tubular);
            showSuccessMessage('Screen removed! Click "Save Changes" to persist.');
        }
    }
}

function removePerforation(index) {
    if (currentMode === 'editing' && currentUnitIndex >= 0 && currentUnitIndex < schematicData.tubulars.length) {
        const tubular = schematicData.tubulars[currentUnitIndex];
        // Note: Perforations are not part of the API spec
        console.log('Perforations not supported in API format yet');
        populateSubElements(tubular);
        showSuccessMessage('Perforation removal not supported in API format.');
    }
}

// Clear sub-component selection
function clearSubSelection() {
    selectedSubType = null;
    selectedSubIndex = -1;
}

// Select sub-component for editing (populate form)
function selectFluid(index) {
    if (currentMode !== 'editing' || currentUnitIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    const fluids = tubular.fluids || [];
    if (index < 0 || index >= fluids.length) return;
    selectedSubType = 'fluid';
    selectedSubIndex = index;
    const f = fluids[index];
    $('#fluid_type').val(f.fluid_type);
    $('#fluid_location').val(f.location || 'inside');
    $('#fluid_top').val(f.top_depth);
    $('#fluid_bottom').val(f.bottom_depth);
    populateSubElements(tubular);
    showUpdateButtonFor('fluid');
}

function selectCement(index) {
    if (currentMode !== 'editing' || currentUnitIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    const cements = tubular.cements || [];
    if (index < 0 || index >= cements.length) return;
    selectedSubType = 'cement';
    selectedSubIndex = index;
    const c = cements[index];
    $('#cement_type').val(c.cement_type);
    $('#cement_location').val(c.location || 'outside');
    $('#cement_top').val(c.top_depth);
    $('#cement_bottom').val(c.bottom_depth);
    populateSubElements(tubular);
    showUpdateButtonFor('cement');
}

function selectPacker(index) {
    if (currentMode !== 'editing' || currentUnitIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    const packers = tubular.packers || [];
    if (index < 0 || index >= packers.length) return;
    selectedSubType = 'packer';
    selectedSubIndex = index;
    const p = packers[index];
    $('#packer_type').val(p.packer_type);
    $('#packer_top').val(p.top_depth);
    $('#packer_bottom').val(p.bottom_depth);
    populateSubElements(tubular);
    showUpdateButtonFor('packer');
}

function selectPlug(index) {
    if (currentMode !== 'editing' || currentUnitIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    const plugs = tubular.plugs || [];
    if (index < 0 || index >= plugs.length) return;
    selectedSubType = 'plug';
    selectedSubIndex = index;
    const p = plugs[index];
    $('#plug_plugtype').val(p.plug_type);
    $('#plug_top').val(p.top_depth);
    $('#plug_bottom').val(p.bottom_depth);
    populateSubElements(tubular);
    showUpdateButtonFor('plug');
}

function selectScreen(index) {
    if (currentMode !== 'editing' || currentUnitIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    const screens = tubular.screens || [];
    if (index < 0 || index >= screens.length) return;
    selectedSubType = 'screen';
    selectedSubIndex = index;
    const s = screens[index];
    $('#screen_type').val(s.screen_type);
    $('#screen_top').val(s.top_depth);
    $('#screen_bottom').val(s.bottom_depth);
    populateSubElements(tubular);
    showUpdateButtonFor('screen');
}

function showUpdateButtonFor(type) {
    $('#update_fluid_btn, #update_cement_btn, #update_packer_btn, #update_plug_btn, #update_screen_btn').hide();
    $('#update_' + type + '_btn').show();
}

// Update selected sub-component from form values (saves to tubular in memory)
function updateSelectedFluid() {
    if (currentMode !== 'editing' || currentUnitIndex < 0 || selectedSubType !== 'fluid' || selectedSubIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    if (!tubular.fluids || selectedSubIndex >= tubular.fluids.length) return;
    const fluid_type = $('#fluid_type').val();
    const location = $('#fluid_location').val();
    const top_depth = parseFloat($('#fluid_top').val());
    const bottom_depth = parseFloat($('#fluid_bottom').val());
    if (!fluid_type || !location || isNaN(top_depth) || isNaN(bottom_depth)) {
        showErrorMessage('Please fill in all fluid fields');
        return;
    }
    tubular.fluids[selectedSubIndex] = { fluid_type, location, top_depth, bottom_depth };
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
    clearSubSelection();
    clearFluidFields();
    $('#update_fluid_btn').hide();
    populateSubElements(tubular);
    showSuccessMessage('Fluid updated. Click "Save Changes" to persist.');
}

function updateSelectedCement() {
    if (currentMode !== 'editing' || currentUnitIndex < 0 || selectedSubType !== 'cement' || selectedSubIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    if (!tubular.cements || selectedSubIndex >= tubular.cements.length) return;
    const cement_type = $('#cement_type').val();
    const location = $('#cement_location').val();
    const top_depth = parseFloat($('#cement_top').val());
    const bottom_depth = parseFloat($('#cement_bottom').val());
    if (!cement_type || !location || isNaN(top_depth) || isNaN(bottom_depth)) {
        showErrorMessage('Please fill in all cement fields');
        return;
    }
    tubular.cements[selectedSubIndex] = { cement_type, location, top_depth, bottom_depth };
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
    clearSubSelection();
    clearCementFields();
    $('#update_cement_btn').hide();
    populateSubElements(tubular);
    showSuccessMessage('Cement updated. Click "Save Changes" to persist.');
}

function updateSelectedPacker() {
    if (currentMode !== 'editing' || currentUnitIndex < 0 || selectedSubType !== 'packer' || selectedSubIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    if (!tubular.packers || selectedSubIndex >= tubular.packers.length) return;
    const packer_type = $('#packer_type').val();
    const top_depth = parseFloat($('#packer_top').val());
    const bottom_depth = parseFloat($('#packer_bottom').val());
    if (!packer_type || isNaN(top_depth) || isNaN(bottom_depth)) {
        showErrorMessage('Please fill in all packer fields');
        return;
    }
    tubular.packers[selectedSubIndex] = { packer_type, top_depth, bottom_depth };
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
    clearSubSelection();
    clearPackerFields();
    $('#update_packer_btn').hide();
    populateSubElements(tubular);
    showSuccessMessage('Packer updated. Click "Save Changes" to persist.');
}

function updateSelectedPlug() {
    if (currentMode !== 'editing' || currentUnitIndex < 0 || selectedSubType !== 'plug' || selectedSubIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    if (!tubular.plugs || selectedSubIndex >= tubular.plugs.length) return;
    const plug_type = $('#plug_plugtype').val();
    const top_depth = parseFloat($('#plug_top').val());
    const bottom_depth = parseFloat($('#plug_bottom').val());
    if (!plug_type || isNaN(top_depth) || isNaN(bottom_depth)) {
        showErrorMessage('Please fill in all plug fields');
        return;
    }
    tubular.plugs[selectedSubIndex] = { plug_type, top_depth, bottom_depth };
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
    clearSubSelection();
    clearPlugFields();
    $('#update_plug_btn').hide();
    populateSubElements(tubular);
    showSuccessMessage('Plug updated. Click "Save Changes" to persist.');
}

function updateSelectedScreen() {
    if (currentMode !== 'editing' || currentUnitIndex < 0 || selectedSubType !== 'screen' || selectedSubIndex < 0) return;
    const tubular = schematicData.tubulars[currentUnitIndex];
    if (!tubular.screens || selectedSubIndex >= tubular.screens.length) return;
    const screen_type = $('#screen_type').val();
    const top_depth = parseFloat($('#screen_top').val());
    const bottom_depth = parseFloat($('#screen_bottom').val());
    if (!screen_type || isNaN(top_depth) || isNaN(bottom_depth)) {
        showErrorMessage('Please fill in all screen fields');
        return;
    }
    tubular.screens[selectedSubIndex] = { screen_type, top_depth, bottom_depth };
    tubular.draw_shoe = $('#draw_shoe').is(':checked');
    tubular.hanger_seal_type = $('#hanger_seal_type').val() || 'double_seal_hanger';
    clearSubSelection();
    clearScreenFields();
    $('#update_screen_btn').hide();
    populateSubElements(tubular);
    showSuccessMessage('Screen updated. Click "Save Changes" to persist.');
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
    $('#json_output_card').show();
    $('#schematic_output_card').show();
    
    // Update unit list display and show management buttons
    updateUnitListDisplay();
    showUnitManagementButtons();
}

/**
 * Hides all schematic UI elements
 */
function hideAllSchematicUI() {
    $('#saved_schematics_section').hide();
    $('#well_schematics_input_card').hide();
    $('#json_output_card').hide();
    $('#schematic_output_card').hide();
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
                uniform_spacing: 0.2
            }
        },
        tubulars: []
    };
    currentUnitIndex = -1;
    currentMode = 'none';
    resetTempArrays();
}

/**
 * Resets UI elements
 */
function resetUI() {
    $('#unit_list').html(`
        <div style="color: #666; font-style: italic; text-align: center; padding: 20px;">
            No units defined yet. Start by adding your first unit below.
        </div>
    `);
    $('#well_schematic_output').html('');
    $('#unit_selector_group, #unit_editing_controls, #unit_creation_controls').hide();
    $('#add_unit_btn, #edit_unit_btn').hide();
    $('#unit_selector').empty().append('<option value="">Select a unit...</option>');
    resetTempArrays();
}

/**
 * Clears form fields
 */
function clearFormFields() {
    $('#unit_name, #unit_top, #unit_bottom, #unit_id, #unit_od, #unit_oh, #hole_top_depth, #hole_bottom_depth, #schematic_name_input').val('');
    $('#unit_type').val('');
    $('#is_tapered').prop('checked', false).trigger('change');
    $('#transition_depth, #bottom_id, #bottom_od').val('');
    $('#draw_shoe').prop('checked', true); // Reset to default
    $('#hanger_seal_type').val('double_seal_hanger'); // Reset to default
    $('#esp_enabled').prop('checked', false);
    $('#esp_top_depth, #esp_bottom_depth').val('');
    $('#esp_section, #esp_fields').hide();
    clearAllSubElementFields();
    // Disable Create New button when schematic name is cleared
    $('#new_schematic_btn').prop('disabled', true);
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
    $('#fluid_type, #fluid_location, #fluid_top, #fluid_bottom').val('');
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
    
    // A-Ring
    if ($('#wellhead_a_enabled').is(':checked')) {
        wellheadValves.A = {
            enabled: true,
            include_left_valves: $('#wellhead_a_left_valves').is(':checked'),
            include_right_valves: $('#wellhead_a_right_valves').is(':checked')
        };
    }
    
    // B-Ring
    if ($('#wellhead_b_enabled').is(':checked')) {
        wellheadValves.B = {
            enabled: true,
            include_left_valves: $('#wellhead_b_left_valves').is(':checked'),
            include_right_valves: $('#wellhead_b_right_valves').is(':checked')
        };
    }
    
    // C-Ring
    if ($('#wellhead_c_enabled').is(':checked')) {
        wellheadValves.C = {
            enabled: true,
            include_left_valves: $('#wellhead_c_left_valves').is(':checked'),
            include_right_valves: $('#wellhead_c_right_valves').is(':checked')
        };
    }
    
    // D-Ring
    if ($('#wellhead_d_enabled').is(':checked')) {
        wellheadValves.D = {
            enabled: true,
            include_left_valves: $('#wellhead_d_left_valves').is(':checked'),
            include_right_valves: $('#wellhead_d_right_valves').is(':checked')
        };
    }
    
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
        uniform_spacing: !isNaN(uniformSpacing) ? uniformSpacing : 0.2
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
 * Populates wellhead valves form from data
 */
function populateWellheadValvesForm(wellheadValves) {
    if (!wellheadValves) {
        return;
    }
    
    $('#wellhead_valves_enabled').prop('checked', wellheadValves.enabled !== false);
    
    if (wellheadValves.A) {
        $('#wellhead_a_enabled').prop('checked', wellheadValves.A.enabled !== false);
        $('#wellhead_a_left_valves').prop('checked', wellheadValves.A.include_left_valves || false);
        $('#wellhead_a_right_valves').prop('checked', wellheadValves.A.include_right_valves !== false);
    }
    
    if (wellheadValves.B) {
        $('#wellhead_b_enabled').prop('checked', wellheadValves.B.enabled !== false);
        $('#wellhead_b_left_valves').prop('checked', wellheadValves.B.include_left_valves || false);
        $('#wellhead_b_right_valves').prop('checked', wellheadValves.B.include_right_valves !== false);
    }
    
    if (wellheadValves.C) {
        $('#wellhead_c_enabled').prop('checked', wellheadValves.C.enabled !== false);
        $('#wellhead_c_left_valves').prop('checked', wellheadValves.C.include_left_valves || false);
        $('#wellhead_c_right_valves').prop('checked', wellheadValves.C.include_right_valves || false);
    }
    
    if (wellheadValves.D) {
        $('#wellhead_d_enabled').prop('checked', wellheadValves.D.enabled !== false);
        $('#wellhead_d_left_valves').prop('checked', wellheadValves.D.include_left_valves || false);
        $('#wellhead_d_right_valves').prop('checked', wellheadValves.D.include_right_valves || false);
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
}

// =============================================================================
// SCHEMATIC GENERATION
// =============================================================================

// transformToApiFormat function removed - data is now stored directly in API format

/**
 * Generates and displays JSON from current data (already in API format)
 */
function generateJSON() {
    $('#json_input_error').text('');
    
    if (schematicData.tubulars.length === 0) {
        $('#json_input_error').text('No units defined. Please add units first or load a saved schematic.');
        $('#generated_json_output').text('');
        return;
    }
    
    // Update well name in schematic data
    const wellName = $('#select_well').val() || 'Well';
    schematicData.well.name = wellName;

    // Update layout, wellhead and xmas tree configuration from form
    schematicData.well.layout = buildLayoutConfig();
    schematicData.well.wellhead_valves = buildWellheadValvesConfig();
    schematicData.well.xmas_tree = buildXmasTreeConfig();

    // Display formatted JSON (data is already in API format)
    const formattedJSON = JSON.stringify(schematicData, null, 2);
    $('#generated_json_output').text(formattedJSON);
    
    // Show the JSON output card
    $('#json_output_card').show();
    $('#json_output_card_body').slideDown();
    
    showSuccessMessage('JSON generated successfully!');
}

/**
 * Copies the generated JSON to clipboard
 */
function copyJSONToClipboard() {
    const jsonText = $('#generated_json_output').text();
    
    if (!jsonText || jsonText.trim() === '') {
        showErrorMessage('No JSON to copy. Please generate JSON first.');
        return;
    }
    
    // Create a temporary textarea element
    const textarea = document.createElement('textarea');
    textarea.value = jsonText;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    
    try {
        document.execCommand('copy');
        showSuccessMessage('JSON copied to clipboard!');
    } catch (err) {
        showErrorMessage('Failed to copy JSON to clipboard.');
        console.error('Copy failed:', err);
    }
    
    document.body.removeChild(textarea);
}

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

    // Update layout, wellhead and xmas tree configuration from form
    schematicData.well.layout = buildLayoutConfig();
    schematicData.well.wellhead_valves = buildWellheadValvesConfig();
    schematicData.well.xmas_tree = buildXmasTreeConfig();

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

$(document).ready(function() {
    // Well selection change
    $('#select_well').on('change', function() {
        checkForSavedSchematics();
    });
    
    // Schematic selection change - show/hide Load button
    $('#saved_schematics_select').on('change', function() {
        const selectedValue = $(this).val();
        if (selectedValue && selectedValue !== '') {
            $('#load_schematic_btn').show();
        } else {
            $('#load_schematic_btn').hide();
        }
    });
    
    // Schematic name input - enable/disable Create New button
    $('#schematic_name_input').on('input', function() {
        const schematicName = $(this).val().trim();
        if (schematicName && schematicName !== '') {
            $('#new_schematic_btn').prop('disabled', false);
        } else {
            $('#new_schematic_btn').prop('disabled', true);
        }
    });
    
    // Initialize Create New button state
    $('#new_schematic_btn').prop('disabled', true);
    
    // Schematic management
    $('#load_schematic_btn').on('click', loadSelectedSchematic);
    $('#new_schematic_btn').on('click', createNewSchematic);
    $('#save_schematic_btn').on('click', saveCurrentSchematic);
    $('#generate_json_btn').on('click', generateJSON);
    $('#copy_json_btn').on('click', copyJSONToClipboard);
    $('#generate_schematic_btn').on('click', generateSchematic);

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
    });
    
    // Close modal when clicking outside
    $('#template_selection_modal').on('click', function(e) {
        if ($(e.target).is('#template_selection_modal')) {
            $(this).hide();
        }
    });
    
    // Unit management - new workflow
    $('#new_unit_btn').on('click', startNewUnitCreation);
    $('#edit_unit_btn').on('click', function() {
        if (currentUnitIndex >= 0) {
            startUnitEditing(currentUnitIndex);
        }
    });
    
    $('#add_unit_btn').on('click', saveCurrentUnit);
    $('#clear_form_btn').on('click', function() {
        if (currentMode === 'creation') {
            cancelUnitEditing();
            } else {
            clearFormFields();
            resetTempArrays();
        }
    });
    
    // Unit editing controls
    $('#save_unit_changes_btn').on('click', saveCurrentUnit);
    $('#delete_current_unit_btn').on('click', deleteCurrentUnit);
    $('#cancel_edit_btn').on('click', cancelUnitEditing);
    
    // Sub-element management
    $('#add_fluid_btn').on('click', addFluid);
    $('#add_cement_btn').on('click', addCement);
    $('#add_packer_btn').on('click', addPacker);
    $('#add_plug_btn').on('click', addPlug);
    $('#add_screen_btn').on('click', addScreen);
    $('#update_fluid_btn').on('click', updateSelectedFluid);
    $('#update_cement_btn').on('click', updateSelectedCement);
    $('#update_packer_btn').on('click', updateSelectedPacker);
    $('#update_plug_btn').on('click', updateSelectedPlug);
    $('#update_screen_btn').on('click', updateSelectedScreen);
    $('#add_perf_btn').on('click', addPerforation);
    
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
    });
    
    // ESP checkbox - show/hide depth fields
    $('#esp_enabled').on('change', function() {
        if ($(this).is(':checked')) {
            $('#esp_fields').show();
        } else {
            $('#esp_fields').hide();
            $('#esp_top_depth, #esp_bottom_depth').val('');
        }
    });
    
    // Tapered casing checkbox
    $('#is_tapered').on('change', function() {
        if ($(this).is(':checked')) {
            $('#tapered_fields').show();
            updateTaperedFields();
        } else {
            $('#tapered_fields').hide();
        }
    });
    
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
    
    // Toggle JSON card collapse/expand
    $('#toggle_json_card_btn').on('click', function() {
        const $body = $('#json_output_card_body');
        const $icon = $('#json_card_toggle_icon');
        if ($body.is(':visible')) {
            $body.slideUp();
            $icon.removeClass('fa-chevron-up').addClass('fa-chevron-down');
        } else {
            $body.slideDown();
            $icon.removeClass('fa-chevron-down').addClass('fa-chevron-up');
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
    populateLayoutForm(schematicData.well.layout);
});