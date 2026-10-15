var graph = new joint.dia.Graph({});
var canvas = document.getElementById('mybuilder');
var selected_cell = null;
var graphScale = 1;
var diagramHistory = [];
var historyIndex = -1;
var savedDiagram = '';
var historyTimer = null;
var restoringDiagram = false;
var inspectorDirty = false;

function portGroup(view, magnet) {
    if (!view || !magnet) return null;
    var portElement = magnet.closest('[port]');
    if (!portElement) return null;
    var portId = portElement.getAttribute('port');
    if (['PrimIn', 'SecIn', 'HeatIn', 'GasIn'].indexOf(portId) !== -1) return 'in';
    if (['PrimOut', 'SecOut', 'HeatOut', 'ElecOut'].indexOf(portId) !== -1) return 'out';
    var port = view.model.getPort && view.model.getPort(portId);
    if (port && port.group) return port.group;
    if ((view.model.get('inPorts') || []).indexOf(portId) !== -1) return 'in';
    if ((view.model.get('outPorts') || []).indexOf(portId) !== -1) return 'out';
    return null;
}

var paper = new joint.dia.Paper({
    el: canvas,
    model: graph,
    width: canvas.clientWidth,
    height: canvas.clientHeight,
    gridSize: 10,
    drawGrid: true,
    linkPinning: false,
    snapLinks: { radius: 50 },
    validateConnection: function (sourceView, sourceMagnet, targetView, targetMagnet) {
        return !!targetView && sourceView.model.id !== targetView.model.id &&
            portGroup(sourceView, sourceMagnet) === 'out' &&
            portGroup(targetView, targetMagnet) === 'in';
    },
    defaultLink: new joint.shapes.devs.Link({
        attrs: { '.marker-target': { d: 'M 10 0 L 0 5 L 10 10 z' } }
    }),
    defaultRouter: { name: 'manhattan', args: { step: 10 } },
    defaultConnector: { name: 'jumpover', size: 10 }
});

function setBuilderStatus(message, dirty) {
    var status = document.getElementById('builder-save-status');
    status.textContent = message;
    status.classList.toggle('is-dirty', !!dirty);
}

function hasUnsavedDiagram() {
    return inspectorDirty || JSON.stringify(graph.toJSON()) !== savedDiagram;
}

function updateHistoryButtons() {
    document.getElementById('builder-undo').disabled = historyIndex <= 0;
    document.getElementById('builder-redo').disabled = historyIndex >= diagramHistory.length - 1;
    var dirty = hasUnsavedDiagram();
    setBuilderStatus(dirty ? 'Unsaved changes' : 'Saved', dirty);
}

function recordDiagramChange() {
    if (restoringDiagram) return;
    clearTimeout(historyTimer);
    historyTimer = null;
    var snapshot = JSON.stringify(graph.toJSON());
    if (snapshot !== diagramHistory[historyIndex]) {
        diagramHistory = diagramHistory.slice(0, historyIndex + 1);
        diagramHistory.push(snapshot);
        if (diagramHistory.length > 50) diagramHistory.shift();
        historyIndex = diagramHistory.length - 1;
    }
    updateHistoryButtons();
}

function queueDiagramChange() {
    if (restoringDiagram) return;
    setBuilderStatus('Unsaved changes', true);
    clearTimeout(historyTimer);
    historyTimer = setTimeout(recordDiagramChange, 250);
}

function resetEditorHistory(markSaved) {
    clearTimeout(historyTimer);
    clearBuilderSelection(true);
    inspectorDirty = false;
    diagramHistory = [JSON.stringify(graph.toJSON())];
    historyIndex = 0;
    if (markSaved) savedDiagram = diagramHistory[0];
    updateHistoryButtons();
}

function markDiagramSaved(snapshot) {
    recordDiagramChange();
    savedDiagram = snapshot;
    updateHistoryButtons();
}

function restoreHistory(index) {
    if (index < 0 || index >= diagramHistory.length) return;
    if (inspectorDirty && !confirm('Discard unsaved changes in the inspector?')) return;
    restoringDiagram = true;
    clearTimeout(historyTimer);
    clearBuilderSelection(true);
    inspectorDirty = false;
    historyIndex = index;
    graph.fromJSON(JSON.parse(diagramHistory[index]));
    restoringDiagram = false;
    updateHistoryButtons();
}

function clearBuilderSelection(force) {
    if (!force && inspectorDirty &&
        !confirm('Discard unsaved changes in the inspector?')) return false;
    if (selected_cell) {
        var oldView = paper.findViewByModel(selected_cell);
        if (oldView) oldView.el.classList.remove('builder-selected');
    }
    selected_cell = null;
    inspectorDirty = false;
    document.getElementById('componentModal').classList.remove('has-selection');
    document.querySelector('.builder-link-editor').hidden = true;
    document.getElementById('builder-delete').disabled = true;
    $('#context-menu').removeClass('show').hide();
    if (!restoringDiagram && historyIndex >= 0) updateHistoryButtons();
    return true;
}

function selectBuilderCell(cell) {
    if (selected_cell && selected_cell.id === cell.id) return true;
    if (inspectorDirty && !confirm('Discard unsaved changes in the inspector?')) return false;
    clearBuilderSelection(true);
    inspectorDirty = false;
    selected_cell = cell;
    canvas.focus({ preventScroll: true });
    var view = paper.findViewByModel(cell);
    if (view) view.el.classList.add('builder-selected');
    document.getElementById('builder-delete').disabled = false;
    if (cell.get('properties')) {
        open_element_parameter(cell);
        document.getElementById('componentModal').classList.add('has-selection');
    } else {
        document.querySelector('.builder-inspector-empty').textContent =
            cell.isLink() ? 'Pipe selected. Choose its circuit below.' :
                'Mixing node selected. Press Delete to remove it.';
        if (cell.isLink()) {
            document.getElementById('builder-link-loop').value = cell.get('loop') || '';
            document.querySelector('.builder-link-editor').hidden = false;
        }
    }
    return true;
}

function delete_element() {
    if (!selected_cell) return;
    if (inspectorDirty && !confirm('Delete this component and its unsaved inspector changes?')) return;
    var cell = selected_cell;
    clearBuilderSelection(true);
    inspectorDirty = false;
    cell.remove();
    recordDiagramChange();
}

function show_parameter_modal() {
    if (selected_cell && selected_cell.get('properties')) {
        document.getElementById('componentModal').classList.add('has-selection');
        document.getElementById('componentModal').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function setZoom(scale) {
    graphScale = Math.max(0.4, Math.min(2.5, scale));
    paper.scale(graphScale, graphScale);
    document.getElementById('builder-zoom-level').textContent = Math.round(graphScale * 100) + '%';
}

function resetView() {
    paper.translate(0, 0);
    setZoom(1);
}

function fitDiagram() {
    if (!graph.getElements().length) {
        resetView();
        return;
    }
    var bounds = graph.getBBox();
    var scale = Math.min((canvas.clientWidth - 60) / bounds.width,
        (canvas.clientHeight - 60) / bounds.height, 2.5);
    setZoom(scale);
    paper.translate(
        (canvas.clientWidth - bounds.width * graphScale) / 2 - bounds.x * graphScale,
        (canvas.clientHeight - bounds.height * graphScale) / 2 - bounds.y * graphScale
    );
}

var panStart = null;
paper.on('blank:pointerdown', function (evt) {
    var translation = paper.translate();
    panStart = { x: evt.clientX, y: evt.clientY, tx: translation.tx, ty: translation.ty };
    canvas.style.cursor = 'grabbing';
});
document.addEventListener('pointermove', function (evt) {
    if (!panStart) return;
    paper.translate(panStart.tx + evt.clientX - panStart.x, panStart.ty + evt.clientY - panStart.y);
});
document.addEventListener('pointerup', function () {
    panStart = null;
    canvas.style.cursor = '';
});
paper.on('blank:mousewheel', function (evt, x, y, delta) {
    evt.preventDefault();
    setZoom(graphScale + (delta > 0 ? 0.1 : -0.1));
});
paper.on('element:pointerclick', function (view) { selectBuilderCell(view.model); });
paper.on('link:pointerclick', function (view) { selectBuilderCell(view.model); });
paper.on('blank:pointerclick', function () { clearBuilderSelection(); });
paper.on('element:pointerup', recordDiagramChange);
paper.on('link:pointerup', recordDiagramChange);
paper.on('element:contextmenu', function (view, evt) {
    evt.preventDefault();
    if (!selectBuilderCell(view.model)) return;
    var rect = document.querySelector('.builder-canvas-panel').getBoundingClientRect();
    $('#context-menu .dropdown-item:first').toggle(!!view.model.get('properties'));
    $('#context-menu').css({ top: evt.clientY - rect.top, left: evt.clientX - rect.left }).addClass('show');
});
paper.on('blank:contextmenu', function (evt) {
    evt.preventDefault();
    clearBuilderSelection();
});
paper.on('link:contextmenu', function (view, evt) {
    evt.preventDefault();
    if (!selectBuilderCell(view.model)) return;
    var rect = document.querySelector('.builder-canvas-panel').getBoundingClientRect();
    $('#context-menu .dropdown-item:first').hide();
    $('#context-menu').css({ top: evt.clientY - rect.top, left: evt.clientX - rect.left }).addClass('show');
});
canvas.addEventListener('contextmenu', function (evt) { evt.preventDefault(); });
graph.on('add remove change', queueDiagramChange);
graph.on('remove', function (cell) {
    if (selected_cell && selected_cell.id === cell.id) clearBuilderSelection(true);
});
function styleDiagramElement(cell) {
    if (!cell.isElement() || !cell.get('properties')) return;
    var view = paper.findViewByModel(cell);
    if (!view) return;
    var type = cell.get('properties').type;
    view.el.setAttribute('data-component-type', type);
    var symbols = {
        production_well: '\uf062', injection_well: '\uf063', reservoir: '\uf1c0',
        esp: '\uf043', injection_pump: '\uf043', booster_pump: '\uf043',
        filter: '\uf0b0', degasser: '\uf0c3', heat_exchanger: '\uf0ec',
        gas_boiler: '\uf06d', electric_boiler: '\uf0e7', heatpump: '\uf2c9',
        heatdemand: '\uf015', chp: '\uf085'
    };
    if (!symbols[type] || view.el.querySelector('.builder-symbol')) return;
    // Draw the symbol on the view, not the model, so older diagrams keep their saved format.
    var symbol = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    symbol.setAttribute('class', 'builder-symbol');
    symbol.setAttribute('x', '7');
    symbol.setAttribute('y', '14');
    symbol.textContent = symbols[type];
    (view.el.querySelector('.rotatable') || view.el).appendChild(symbol);
}
function styleDiagramCell(cell) {
    if (cell.isLink()) {
        var view = paper.findViewByModel(cell);
        if (view) view.el.setAttribute('data-loop', cell.get('loop') || '');
    } else {
        styleDiagramElement(cell);
    }
}
graph.on('add', styleDiagramCell);
graph.on('change:loop', styleDiagramCell);
graph.on('reset', function () {
    graph.getCells().forEach(styleDiagramCell);
});

document.getElementById('builder-undo').addEventListener('click', function () {
    recordDiagramChange();
    restoreHistory(historyIndex - 1);
});
document.getElementById('builder-redo').addEventListener('click', function () {
    recordDiagramChange();
    restoreHistory(historyIndex + 1);
});
document.getElementById('builder-zoom-in').addEventListener('click', function () { setZoom(graphScale + 0.1); });
document.getElementById('builder-zoom-out').addEventListener('click', function () { setZoom(graphScale - 0.1); });
document.getElementById('builder-fit').addEventListener('click', fitDiagram);
document.getElementById('builder-reset-view').addEventListener('click', resetView);
document.getElementById('builder-delete').addEventListener('click', delete_element);
document.addEventListener('keydown', function (evt) {
    var editing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) ||
        document.activeElement.isContentEditable;
    if (editing) return;
    if ((evt.key === 'Delete' || evt.key === 'Backspace') && selected_cell) {
        evt.preventDefault();
        delete_element();
    } else if ((evt.ctrlKey || evt.metaKey) && evt.key.toLowerCase() === 'z') {
        evt.preventDefault();
        recordDiagramChange();
        restoreHistory(historyIndex + (evt.shiftKey ? 1 : -1));
    } else if ((evt.ctrlKey || evt.metaKey) && evt.key.toLowerCase() === 'y') {
        evt.preventDefault();
        recordDiagramChange();
        restoreHistory(historyIndex + 1);
    }
});

document.querySelectorAll('.builder-item').forEach(function (button) {
    button.addEventListener('click', function () {
        var center = paper.clientToLocalPoint(
            canvas.getBoundingClientRect().left + canvas.clientWidth / 2,
            canvas.getBoundingClientRect().top + canvas.clientHeight / 2
        );
        var offset = graph.getElements().length % 8;
        addComponentFromPalette(button.dataset.component, {
            x: Math.round(center.x + (offset % 4 - 1.5) * 120),
            y: Math.round(center.y + (Math.floor(offset / 4) - 0.5) * 90)
        });
    });
    button.addEventListener('dragstart', function (evt) {
        evt.dataTransfer.setData('text/plain', button.dataset.component);
        evt.dataTransfer.effectAllowed = 'copy';
    });
});
canvas.addEventListener('dragover', function (evt) {
    evt.preventDefault();
    evt.dataTransfer.dropEffect = 'copy';
    canvas.classList.add('drag-over');
});
canvas.addEventListener('dragleave', function () { canvas.classList.remove('drag-over'); });
canvas.addEventListener('drop', function (evt) {
    evt.preventDefault();
    canvas.classList.remove('drag-over');
    var type = evt.dataTransfer.getData('text/plain');
    if (!Array.from(document.querySelectorAll('.builder-item')).some(function (button) {
        return button.dataset.component === type;
    })) {
        alert('Drag a component from the palette.');
        return;
    }
    var position = paper.clientToLocalPoint(evt.clientX, evt.clientY);
    addComponentFromPalette(type, { x: position.x, y: position.y });
});
document.getElementById('builder-component-search').addEventListener('input', function (evt) {
    var query = evt.target.value.trim().toLowerCase();
    document.querySelectorAll('.builder-palette-group').forEach(function (group) {
        var visible = false;
        group.querySelectorAll('.builder-item').forEach(function (button) {
            button.hidden = button.textContent.toLowerCase().indexOf(query) === -1;
            visible = visible || !button.hidden;
        });
        group.hidden = !visible;
    });
});
document.getElementById('builder-field-search').addEventListener('input', function (evt) {
    var query = evt.target.value.trim().toLowerCase();
    document.querySelectorAll('.builder-inspector .table tr').forEach(function (row) {
        row.hidden = row.textContent.toLowerCase().indexOf(query) === -1;
    });
});
document.getElementById('componentModal').addEventListener('input', function (evt) {
    if (evt.target.id === 'builder-field-search' || evt.target.id === 'builder-link-loop') return;
    inspectorDirty = true;
    setBuilderStatus('Unsaved inspector changes', true);
});
document.getElementById('componentModal').addEventListener('change', function (evt) {
    if (evt.target.id === 'builder-link-loop' ||
        (evt.target.tagName === 'SELECT' && evt.target.id.indexOf('select_') === 0)) return;
    inspectorDirty = true;
    setBuilderStatus('Unsaved inspector changes', true);
});
document.getElementById('builder-link-loop').addEventListener('change', function (evt) {
    if (!selected_cell || !selected_cell.isLink()) return;
    if (evt.target.value) {
        selected_cell.set('loop', evt.target.value);
    } else {
        selected_cell.unset('loop');
    }
    recordDiagramChange();
});
document.querySelectorAll('.builder-inspector .table tr').forEach(function (row) {
    var label = row.querySelector('td:first-child');
    var field = row.querySelector('td:nth-child(2) input, td:nth-child(2) select');
    if (!label || !field) return;
    var text = label.textContent.trim();
    field.setAttribute('aria-label', text);
    var unit = text.match(/\[([^\]]+)\]$/);
    if (!unit) return;
    label.querySelector('span').textContent = text.slice(0, unit.index).trim();
    var wrapper = document.createElement('span');
    wrapper.className = 'builder-input-unit';
    field.parentNode.insertBefore(wrapper, field);
    wrapper.appendChild(field);
    var suffix = document.createElement('span');
    suffix.className = 'builder-field-unit';
    suffix.textContent = unit[1];
    wrapper.appendChild(suffix);
});
var canvasPanel = document.querySelector('.builder-canvas-panel');
function resizeBuilderCanvas() {
    var panelStyle = window.getComputedStyle(canvasPanel);
    var canvasStyle = window.getComputedStyle(canvas);
    var width = Math.floor(canvasPanel.clientWidth -
        parseFloat(panelStyle.paddingLeft) - parseFloat(panelStyle.paddingRight) -
        parseFloat(canvasStyle.borderLeftWidth) - parseFloat(canvasStyle.borderRightWidth));
    if (width <= 0) return;
    var height = Math.round(Math.max(480, Math.min(window.innerHeight * 0.7, 760)));
    if (canvas.clientWidth !== width || canvas.clientHeight !== height) {
        paper.setDimensions(width, height);
    }
}
if (window.ResizeObserver) {
    new ResizeObserver(resizeBuilderCanvas).observe(canvasPanel);
}
window.addEventListener('resize', resizeBuilderCanvas);
resizeBuilderCanvas();
window.addEventListener('beforeunload', function (evt) {
    if (!hasUnsavedDiagram()) return;
    evt.preventDefault();
    evt.returnValue = '';
});
resetEditorHistory(true);
