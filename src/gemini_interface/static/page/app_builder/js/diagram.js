var namespace = joint.shapes;

var graph = new joint.dia.Graph({});

var paper = new joint.dia.Paper({
    el: document.getElementById('mybuilder'),
    model: graph,
    width: window.innerWeight,
    height: 600,
    gridSize: 10,
    drawGrid: true,
    defaultLink: new joint.shapes.devs.Link({
        attrs: {
            ".marker-target": {
                d: "M 10 0 L 0 5 L 10 10 z",
            },
        }
    }),
    snapLinks: { radius: 50 }

});

// LINE
paper.options.defaultRouter = {
    name: "manhattan",
    args: {
        step: 10,
    },
};

paper.options.defaultConnector = { name: "jumpover", size: 10 };

// ZOOOM
graphScale = 1
paper.on('blank:mousewheel', function (evt, x, y, delta) {
    if (delta > 0) {
        graphScale = graphScale + 0.1
    } else {
        graphScale = graphScale - 0.1
    }
    paper.scale(graphScale)
});


paper.on({
    'element:contextmenu': onElementRightClick,
    'blank:contextmenu': onBlankRightClick
});

selected_element = ''
selected_cell = null

function onElementRightClick(view) {
    cell = graph.getCell(view.model.id)

    selected_cell = cell
    selected_element = 'element'

    open_element_parameter(selected_cell)
}

function onBlankRightClick(view) {
    selected_cell = null
    selected_element = ''
}


function delete_element(){
    graph.removeCells(selected_cell)
}

function show_parameter_modal(){
    $('#componentModal').modal('show');

}



$('.jumbotron').on('contextmenu', function(e) {
    var top = e.pageY - 1000;
    var left = e.pageX - 400;

    if (selected_element==''){
        display = "none"
    }else{
        display = "block"
    }

    $("#context-menu").css({
      display: display,
      top: top,
      left: left
    }).addClass("show");
    return false; //blocks default Webbrowser right click menu
  }).on("click", function() {
    $("#context-menu").removeClass("show").hide();
  });
  
  $("#context-menu a").on("click", function() {
    $(this).parent().removeClass("show").hide();
  });


