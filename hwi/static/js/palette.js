var dragSrcEl = null;
var svg = null;
var x = null;
var y = null;

function handleDragStart(e) {
    this.style.opacity = '0.4';  // this / e.target is the source node.
    dragSrcEl = this;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.innerHTML);
}


function handleDragOver(e) {
    if (e.preventDefault) {
    e.preventDefault(); // Necessary. Allows us to drop.
    }

    e.dataTransfer.dropEffect = 'move';  

    return false;
}

function handleDragEnter(e) {
    // this / e.target is the current hover target.
    this.classList.add('over');
}

function handleDragLeave(e) {
    // this / e.target is previous target element.
    this.classList.remove('over');  
}

function handleDrop(e) {
  // this / e.target is current target element.

    if (e.stopPropagation) {
        e.stopPropagation(); // stops the browser from redirecting.
    }

    svg_origin = document.querySelector('#graph svg').getBoundingClientRect();

    svg_topleft_x = svg_origin.x;
    svg_topleft_y = svg_origin.y;
    if (map == null){
        var nodex = e.clientX - svg_topleft_x - margin.left;
        var nodey = e.clientY - svg_topleft_y - margin.top;
    }else{
        var layer_coords = map.mouseEventToLayerPoint(e) 
        var nodex = layer_coords.x;
        var nodey = layer_coords.y;
    }

    var g = dragSrcEl.querySelector("g");


    console.log("Dropping "+g+" on "+nodex+" , "+nodey+".");
    
    var newnode = svg.append('g')
      .html(g.innerHTML)
      .attr('class', 'node')
      .attr("transform", function(d) { 
          return "translate(" + nodex + "," + nodey + ")"; 
        }); 
    
    var date = new Date(); // for now
    var default_name = "Node " + date.getHours() + ":" + date.getMinutes() + ":" + date.getSeconds();

    var type_id = newnode.select('path').attr('resourcetype')

    for (var i=0; i<template.templatetypes.length; i++){
        if (parseInt(type_id) == template.templatetypes[i]['type_id']){
            var t = template.templatetypes[i]
        }
    }
   


    if (map == null){ 
        if (currentTransform == null){
            var realnodex = xScale.invert(nodex)
        }else{
            var realnodex = xScale.invert(currentTransform.invertX(nodex))
        }

        if (currentTransform == null){
            var realnodey = yScale.invert(nodey)
        }else{
            var realnodey = yScale.invert(currentTransform.invertY(nodey))
        }
    }else{
        realcoords = map.layerPointToLatLng(new L.Point(nodex, nodey))
        realnodex = realcoords.lng;
        realnodey = realcoords.lat;

    }

    node_id = add_node(default_name, type_id, realnodex, realnodey)

    var data = {
        id          : node_id,
        name        : default_name,
        type        : t,
        x           : realnodex,
        y           : realnodey, 
        description : "",
        group       : 1, //These will be phased out
        res_type    : 'node'
    }

    if (map != null){
        data.LatLng = new L.LatLng(realnodey, realnodex);

        data.x_ = map.latLngToLayerPoint(data.LatLng).x;
        data.y_ = map.latLngToLayerPoint(data.LatLng).y;

    }

    newnode.remove()

    nodes_.push(data)

    set_visible_nodes()

    redraw_nodes()

    if (map != null){
        update()
    }



  return false;
}

function handleDragEnd(e) {
  // this/e.target is the source node.

   this.style.opacity = '1'; 

  var types = document.querySelectorAll('#palette .draggablebox');
  [].forEach.call(types, function (typ) {
    typ.classList.remove('over');
  });
}


function activateShapes(){
    var types = document.querySelectorAll('#palette .draggablebox');
    [].forEach.call(types, function(typ) {
      typ.addEventListener('dragstart', handleDragStart, false);
      typ.addEventListener('dragenter', handleDragEnter, false);
      typ.addEventListener('dragleave', handleDragLeave, false);
      typ.addEventListener('dragend', handleDragEnd, false);
    });
}

function activateCanvas(){
    document.querySelector('#graph').addEventListener('dragover', handleDragOver, false);
    document.querySelector('#graph').addEventListener('drop', handleDrop, false);

}

var nodetip = d3.tip()
  .attr('class', 'd3tip')
  .offset([-10,20])
  .html(function(d) {
    return "<span>" + d.type_name + "</spsn>";
  })

function loadShapesIntoPalette(){

    var palette = d3.select("#palette")
    
    svg = d3.select("#graph svg")

    var typedict = {} 
    if (template.templatetypes.length > 0){
        for (i=0; i<template.templatetypes.length; i++){
            var tt = template.templatetypes[i]
            var rt = tt.resource_type
    
            if (typedict[rt] == undefined){
                typedict[rt] = [tt]
            }else{
                typedict[rt].push(tt)
            }
        }
    }else{
        typedict['NODE'] = [{'type_name': 'Default Node',
                             'layout': {'shape':'circle', 'color':'black', 'width': '15', 'height': '15'}
                       }]
    }
    
    // Declare the shapes
    var node = palette.selectAll("div.shapecontainer")
      .data(typedict['NODE'])

    // Enter the shapes.
    var nodeEnterSvg = node.enter().append("div")
      .attr("class", "shapecontainer")
      .append('span')
      .attr('class', 'draggablebox')
      .attr('draggable', 'true')
      .append("svg")
      .call(nodetip)

      grad = nodeEnterSvg.append('defs')
        .append('radialGradient')
        .attr('id', function(d){return 'nodegradient_'+d.type_name.replace(new RegExp(" ", 'g'), '')})
      grad.append('stop')
        .attr('offset', '10%')
        .attr('stop-color', function(d) {
            if (d.layout.color != undefined){return d.layout.color}else{return 'black'}
        })
        .attr('stop-opacity', "0.6")

      grad.append('stop')
        .attr('offset', '50%')
        .attr('stop-color', function(d) {
            if (d.layout.color != undefined){return d.layout.color}else{return 'black'}
        })
        .attr('stop-opacity', "0.8")

      grad.append('stop')
        .attr('offset', '40%')
        .attr('stop-color', function(d) {
            if (d.layout.color != undefined){return d.layout.color}else{return 'black'}
        })


      nodeEnterSvg.attr("class", "palettesvg")
      .append('g')
      .attr('class', 'type')
      .attr('shape', function(d){if (d.layout.shape != undefined){return d.layout.shape}else{return 'circle'}})
      .attr("transform", function(d) { return "translate(15,15)"; })
      .append("path")
      .attr('resourcetype', function(d){return d.type_id})
      .style("stroke", function(d) {
          if (d.layout.border != undefined){return d.layout.border}else{return 'black'}
      })
      .style("fill", function(d) {
          return "url(#nodegradient_"+d.type_name.replace(new RegExp(" ", 'g'), '')+")"
          //if (d.layout.color != undefined){return d.layout.color}else{return 'black'}
      })
      .attr("d", d3.symbol()
         .size(function(d) { 
             var height = d.layout.height
             if (height == undefined){
                 height = 15
             }
             var width = d.layout.width
             if (width == undefined){
                 width = 15
             }

             return height * width; } )
         .type(function(d) { if
           (d.layout.shape == "circle") { return d3.symbolCircle; } else if
           (d.layout.shape == "diamond") { return d3.symbolDiamond;} else if
           (d.layout.shape == "cross") { return d3.symbolCross;} else if
           (d.layout.shape == "triangle") { return d3.symbolTriangle;} else if
           (d.layout.shape == "square") { return d3.symbolSquare;} else if
           (d.layout.shape == "star") { return d3.symbolStar;} else if
           (d.layout.shape == "wye") { return d3.symbolWye;} else
           { return d3.symbolCircle; }
         }))
         .on('mouseover', function(d){nodetip.show(d)})
         .on('mouseout', function(d){nodetip.hide(d)})

    //Make the shapes in the palette draggable.
    activateShapes();
    activateCanvas();
    
};


loadShapesIntoPalette()
