var map = null;

var margin = {'top': 60, 'right': 40, 'bottom': 60, 'left': 100};

var graph_width = document.getElementById('graph').clientWidth;

var width  = (graph_width - margin.left - margin.right);
var height = (700-margin.top - margin.bottom);
var colors = d3.scaleOrdinal(d3.schemeCategory10);

var yScale = null;
var xScale = null;

var reset_scales = function(){
    //`ransform functions, used to convert the Hydra coordinates
    //to coodrinates on the d3 svg
    yScale = d3.scaleLinear()
                           .domain([max_y, min_y ])
                           .range([height,0]);
    xScale = d3.scaleLinear()
                          .domain([min_x, max_x])
                          .range([0,width]);
}

reset_scales()

function dragged(d) {
    if( d3.select(this).classed('selected') == false){

        return
    }

    var mouse = d3.mouse(svg.node());

    if (currentTransform == null){
        d.x = xScale.invert(mouse[0]);
        d.y = yScale.invert(mouse[1]);
        node.attr("transform", function(d){
            return "translate(" + xScale(d.x) + "," + yScale(d.y) + ")";
        });
    }else{
        d.x = xScale.invert(currentTransform.invertX(mouse[0]));
        d.y = yScale.invert(currentTransform.invertY(mouse[1]));
        node.attr("transform", function(d){
            return "translate(" + currentTransform.applyX(xScale(d.x)) + "," + currentTransform.applyY(yScale(d.y)) + ")";
        });
    }
    tick()
}

//Node drag
var drag = d3.drag()
         .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended);

 //Set up the force layout
var force = d3.forceSimulation()
            .force("link", d3.forceLink().id(function(d) { return d.id }))

//Append a SVG to the body of the html page. Assign this SVG as an object to svg
var svg = d3.select("#graph").append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height+ margin.top + margin.bottom)
    .attr("transform","translate(" + margin.left + "," + margin.top + ")")
    .on("click", function(d){
        svg.selectAll(".node").each(function(d){tip.hide(d)})
        svg.selectAll(".node path").style('stroke', "");
        svg.selectAll(".node path").style('stroke-width',  "");
        svg.selectAll("path.selected").attr("d", normalnode)
        svg.selectAll("path.selected").classed("selected", false)
        d3.selectAll('.node').on("mousedown.drag", null);
        
        $("#data").html("No Resource Selected.")
        current_res = null; 
        current_res_type = null;

        if (drag_line != null){
            drag_line.remove()
            drag_line = null
            start_node = null;
        }
    })
    .on("mousemove", function(){
    if (drag_line != null){
        if (currentTransform){
            drag_line.attr('d', 'M' + currentTransform.applyX(xScale(start_node.datum().x)) + ',' + currentTransform.applyY(yScale(start_node.datum().y)) + 'L' + d3.mouse(svg.node())[0] + ',' + d3.mouse(svg.node())[1]);
        }else{
            drag_line.attr('d', 'M' + xScale(start_node.datum().x) + ',' + yScale(start_node.datum().y) + 'L' + d3.mouse(svg.node())[0] + ',' + d3.mouse(svg.node())[1]);
        }
    }
    })
    .call(tip)


//Creates the graph data structure out of the json data
force.restart();

var tick = function() {
    if ((d3.event == null || d3.event.transform == undefined) && currentTransform == null){

        if (link != undefined){

            link
            .attr('x1', function (d) { return xScale(d.source.x); })
            .attr('y1', function (d) { return yScale(d.source.y); })
            .attr('x2', function (d) { return xScale(d.target.x); })
            .attr('y2', function (d) { return yScale(d.target.y); })
        }

        if (node != undefined){
            node.attr("transform", function(d){
                return "translate(" + xScale(d.x) + "," + yScale(d.y) + ")";
            });
        }

        if (text != undefined){
            text.attr("transform", function (d) {
                    return "translate(" + xScale(d.x)+14 + "," + yScale(d.y) + ")";
                });
        }
    }else{
        zoom();
    }
    force.stop()
}

//Do the same with the circles for the nodes - no
var node = null; 
var link = null; 
var text = null;
var start_node = null;

var redraw_nodes = function(){
    
   svg.selectAll(".node").remove()

    node = svg.selectAll(".node")
        .data(visible_nodes)
        .enter().append("g")
        .classed("node", true)
        .attr("id", function(d) {return 'schematicnode_'+d.id;})
        .attr('shape', function(d){
            if (d.type.layout.shape != undefined){
                return d.type.layout.shape
            }else{
                return 'circle'
            }})
        .attr('resourcetype', function(d){return d.type.type_id})
    
        node
        .append('path')
        .style("fill", function(d) {
            var l = d.type.layout;
            if (l.color != undefined){return l.color}else{return 'black'}
          })

        .attr("d", normalnode)
        .on('mouseover', node_mouse_in) //Added
        .on('mouseout', node_mouse_out) //Added
        .on("click", nodes_mouse_click)
        .on("dblclick", nodes_mouse_double_click)
        .on('contextmenu', d3.contextMenu(menu));

    text = svg.append("g").selectAll(".node")
        .data(visible_nodes)
        .enter().append("text")
        .text(function(d) { return d.name; })
        .style("visibility", "hidden")
        .style("font", "12px sans-serif");

    tick()
}

var redraw_links = function(){

    visible_links.forEach(function(d) {
        if (d.type.layout == undefined){
            d.type.layout = {}
        }else{
            if (typeof(d.type.layout) == 'string'){
                d.type.layout = JSON.parse(d.type.layout)
            }
        }
    });

   svg.selectAll(".link").remove()
    //Create all the line svgs but without locations yet
    link = svg.selectAll(".link")
        .data(visible_links)
        .enter().append("line")
        .attr("id", function(d) {return 'schematiclink_'+d.id;})
        .attr("class", "link")
        .style("stroke-dasharray", function(d){
            if (d.type.layout['linestyle'] != undefined){
                var style = d.type.layout['linestyle']
                if (style == 'dashed'){
                        return (4, 4)
                }else if (style == 'dotted'){
                        return (2, 2)
                }else{
                        return ""
                }
                }else{
                    return ''
                }
        })
         .style('stroke-width',  function(d) { 
              if (d.type.layout['width'] != undefined){return d.type.layout['width']+'px'}else{return '2px'}
        })
         .style('stroke',  function(d) { 
              if (d.type.layout['color'] != undefined){return d.type.layout['color']}else{return 'black'}
        })
        .on('mouseover', link_mouse_in)
        .on('mouseout', link_mouse_out)
        .on("click", links_mouse_click);
   tick() 
}


redraw_links()
redraw_nodes()

force.nodes(visible_nodes).on('tick', tick)
force.force('link').links(visible_links)
tick()

var zoom = function(){

    if (d3.event == null){
        if (currentTransform != null){
            var transform = currentTransform;
        }else{
            return;
        }
    }else{
        var transform = d3.event.transform;
        if (transform != undefined){
            currentTransform = transform;
        }else{
            var transform = currentTransform;
        }
    }

    if (link != undefined){

        link
        .attr('x1', function (d) { return transform.applyX(xScale(d.source.x)); })
        .attr('y1', function (d) { return transform.applyY(yScale(d.source.y)); })
        .attr('x2', function (d) { return transform.applyX(xScale(d.target.x)); })
        .attr('y2', function (d) { return transform.applyY(yScale(d.target.y)); })
    }

    if (node != undefined){
        node.attr("transform", function(d){
            return "translate(" + transform.applyX(xScale(d.x)) + "," + transform.applyY(yScale(d.y)) + ")";
        });
    }
    
    if (text != undefined){
        text.attr("transform", function (d) {
                return "translate(" + transform.applyX(self.xScale(d.x))+14 + "," + transform.applyY(self.yScale(d.y)) + ")";
            });
    }
}

svg.call(d3.zoom()
       .scaleExtent([0.01,100])
        .on("zoom", zoom));


var create_force_layout = function(){
    d3.select('#create-force-layout .fa-spinner').classed('hidden', false)
    d3.select('#create-force-layout .fa-bomb').classed('hidden', true)
    
    //Add force layout properties to the force simulation
    force.force("charge", d3.forceManyBody())
        .force("center", d3.forceCenter(width / 2, height / 2));

    force.nodes(visible_nodes).on('tick', forcetick)
    force.on('end', show_force_save)

    svg.call(d3.zoom()
       .scaleExtent([0.1,8])
        .on("zoom", forcezoom));

    force.restart();

}

var show_force_save = function(){
    d3.select('#create-force-layout .fa-spinner').classed('hidden', true)
    d3.select('#create-force-layout .fa-bomb').classed('hidden', false)

    d3.select('#save-force-layout').classed('hidden', false)
    d3.select('#create-force-layout').classed('hidden', true)
    
    
}

var show_force_create = function(){
    d3.select('#save-force-layout').classed('hidden', true) 
    d3.select('#create-force-layout').classed('hidden', false)
}

var create_static_layout = function(){


    d3.select('#save-force-layout .fa-spinner').classed('hidden', false)
    d3.select('#save-force-layout .fa-save').classed('hidden', true)

    //`ransform functions, used to convert the Hydra coordinates
    //to coodrinates on the d3 svg
    //yScale = d3.scaleLinear()
    //                       .domain([height, 0 ])
    //                       .range([height,0]);
    //xScale = d3.scaleLinear()
    //                      .domain([0, width])
    //                      .range([0,width]);

    //Add force layout properties to the force simulation
    force.force("charge", null)
        .force("center", null);

    force.nodes(visible_nodes).on('tick', tick)

    svg.call(d3.zoom()
       .scaleExtent([0.1,8])
        .on("zoom", zoom));

    force.restart();


    for (var i=0; i<visible_nodes.length; i++){
        var n = visible_nodes[i]
        update_node(n.id, n.name, n.x, n.y)
    }
        
    d3.select('#save-force-layout .fa-spinner').classed('hidden', true)
    d3.select('#save-force-layout .fa-save').classed('hidden', false)

    show_force_create()

}

function forcetick() {

        link
        .attr('x1', function (d) { return d.source.x; })
        .attr('y1', function (d) { return d.source.y; })
        .attr('x2', function (d) { return d.target.x; })
        .attr('y2', function (d) { return d.target.y; })

        node.attr("transform", function(d){
            return "translate(" + d.x + "," + d.y + ")";
        });

        text.attr("transform", function (d) {
                return "translate(" + d.x+14 + "," + d.y + ")";
            });
  }

//Need a different zoom function for force layout because there's no scales
//required, as there are no x,y coordinates 
var forcezoom = function(){

    var transform = d3.event.transform

    link
        .attr('x1', function (d) { return transform.applyX(d.source.x); })
        .attr('y1', function (d) { return transform.applyY(d.source.y); })
        .attr('x2', function (d) { return transform.applyX(d.target.x); })
        .attr('y2', function (d) { return transform.applyY(d.target.y); })

    node.attr("transform", function(d){
        return "translate(" + transform.applyX(d.x) + "," + transform.applyY(d.y) + ")";

    });
}

d3.select('#create-force-layout').on('click', create_force_layout)
d3.select('#save-force-layout').on('click', create_static_layout)
