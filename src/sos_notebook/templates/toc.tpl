{%- block footer -%}
<script>
   //---------------------------------------------------------------------
   //......... utilitary functions............
   var liveNotebook = !(typeof IPython == "undefined")

   function incr_lbl(ary, h_idx) { //increment heading label  w/ h_idx (zero based)
     ary[h_idx]++;
     for (var j = h_idx + 1; j < ary.length; j++) {
       ary[j] = 0;
     }
     return ary.slice(0, h_idx + 1);
   }

   function removeMathJaxPreview(elt) {
     elt.find("script[type='math/tex']").each(
       function(i, e) {
         $(e).replaceWith('$' + $(e).text() + '$');
       })
     elt.find("span.MathJax_Preview").remove()
     elt.find("span.MathJax").remove()
     return elt
   }


   var make_link = function(h, num_lbl) {
     var a = $("<a/>");
     a.attr("href", '#' + h.attr('id'));
     // get the text *excluding* the link text, whatever it may be
     var hclone = h.clone();
     hclone = removeMathJaxPreview(hclone);
     if (num_lbl) {
       hclone.prepend(num_lbl);
     }
     hclone.children().last().remove(); // remove the last child (that is the automatic anchor)
     hclone.find("a[name]").remove(); //remove all named anchors
     a.html(hclone.html());
     a.on('click', function() {
       setTimeout(function() {
         $.ajax()
       }, 100); //workaround for  https://github.com/jupyter/notebook/issues/699
       if (liveNotebook) {
         IPython.notebook.get_selected_cell().unselect(); //unselect current cell
         var new_selected_cell = $("[id='" + h.attr('id') + "']").parents('.unselected').switchClass('unselected', 'selected')
         new_selected_cell.data('cell').selected = true;
         var cell = new_selected_cell.data('cell') // IPython.notebook.get_selected_cell()
         highlight_toc_item("toc_link_click", {
           cell: cell
         })
       }
     })
     return a;
   };


   var make_link_originalid = function(h, num_lbl) {
     var a = $("<a/>");
     a.attr("href", '#' + h.attr('saveid'));
     // add a data attribute so that other code (e.g. collapsible_headings) can use it
     a.attr('data-toc-modified-id', h.attr('id'));
     // get the text *excluding* the link text, whatever it may be
     var hclone = h.clone();
     hclone = removeMathJaxPreview(hclone);
     if (num_lbl) {
       hclone.prepend(num_lbl);
     }
     hclone.children().last().remove(); // remove the last child (that is the automatic anchor)
     hclone.find("a[name]").remove(); //remove all named anchors
     a.html(hclone.html());
     a.on('click', function() {
       setTimeout(function() {
         $.ajax()
       }, 100)
     }) //workaround for  https://github.com/jupyter/notebook/issues/699
     return a;
   }


   var ol_depth = function(element) {
     // get depth of nested ol
     var d = 0;
     while (element.prop("tagName").toLowerCase() == 'ol') {
       d += 1;
       element = element.parent();
     }
     return d;
   };


   function highlight_toc_item(evt, data) {
     var c = data.cell.element; //
     if (c) {
       var ll = $(c).find(':header')
       if (ll.length == 0) {
         var ll = $(c).prevAll().find(':header')
       }
       var elt = ll[ll.length - 1]
       if (elt) {
         var highlighted_item = $(toc).find('a[href="#' + elt.id + '"]')
         if (evt.type == "execute") {
           // remove the selected class and add execute class
           // il the cell is selected again, it will be highligted as selected+running
           highlighted_item.removeClass('toc-item-highlight-select').addClass('toc-item-highlight-execute')
           //console.log("->>> highlighted_item class",highlighted_item.attr('class'))
         } else {
           $(toc).find('.toc-item-highlight-select').removeClass('toc-item-highlight-select')
           highlighted_item.addClass('toc-item-highlight-select')
         }
       }
     }
   }



   var create_navigate_menu = function(callback) {
     $('#kernel_menu').parent().after('<li id="Navigate"/>')
     $('#Navigate').addClass('dropdown').append($('<a/>').attr('href', '#').attr('id', 'Navigate_sub'))
     $('#Navigate_sub').text('Navigate').addClass('dropdown-toggle').attr('data-toggle', 'dropdown')
     $('#Navigate').append($('<ul/>').attr('id', 'Navigate_menu').addClass('dropdown-menu')
       .append($("<div/>").attr("id", "navigate_menu").addClass('toc')))

     callback && callback();
   }

   function setNotebookWidth(cfg, st) {
     //cfg.widenNotebook  = false; 
     if ($('#toc-wrapper').is(':visible')) {
       $('#notebook-container').css('margin-left', $('#toc-wrapper').width() + 30)
       $('#notebook-container').css('width', $('#notebook').width() - $('#toc-wrapper').width() - 30)
     } else {
       if (cfg.widenNotebook) {
         $('#notebook-container').css('margin-left', 30);
         $('#notebook-container').css('width', $('#notebook').width() - 30);
       } else { // original width
         $("#notebook-container").css({
           'width': "82%",
           'margin-left': 'auto'
         })
       }
     }
   }

   var create_toc_div = function(cfg, st) {
     var toc_wrapper = $('<div id="toc-wrapper"/>')
       .append(
         $('<div id="toc-header"/>')
         .addClass("header")
         .append(
           $("<img/>", {
             src: 'http://vatlab.github.io/sos-docs/img/sos_icon.svg'
           })
           .attr("href", "http://vatlab.github.io/sos-docs/index.html#documentation")
           .attr('height', '32')
           .attr('width', '32')
           .attr('style', "border:0px;margin-right:5px;vertical-align:bottom")
         ).append(
           $("<span/>")
           .html("&nbsp;&nbsp")
         ).append(
           $("<a/>")
           .attr("href", "http://vatlab.github.io/sos-docs/index.html#documentation")
           .text("Home")
         ).append($("<form/>").attr('class', 'search-form').attr('action', '../../search.html')
           .append($("<input/>").attr("type", "text").attr('name', 'q').attr('id', 'tipue_search_input').attr('style', 'width:95%;margin-top:9px').attr('placeholder', 'search').attr('pattern', '.{3,}')))
       ).append(
         $("<div/>").attr("id", "toc").addClass('toc')
       )

     $("body").append(toc_wrapper);

     $('#toc-wrapper').resizable({
       handles: 'e',
       resize: function(event, ui) {
         setNotebookWidth(cfg, st)
         $(this).css('height', '100%');
       },
       start: function(event, ui) {
         $(this).width($(this).width());
         //$(this).css('position', 'fixed');
       },
       stop: function(event, ui) {
         // Ensure position is fixed (again)
         //$(this).css('position', 'fixed');
         $(this).css('height', '100%');
         $('#toc').css('height', $('#toc-wrapper').height() - $("#toc-header").height());

       }
     })


     // Ensure position is fixed
     $('#toc-wrapper').css('position', 'fixed');

     // if toc-wrapper is undefined (first run(?), then hide it)
     if ($('#toc-wrapper').css('display') == undefined) $('#toc-wrapper').css('display', "none") //block
     //};

     $('#site').bind('siteHeight', function() {
       if (cfg.sideBar) $('#toc-wrapper').css('height', $('#site').height());
     })

     $('#site').trigger('siteHeight');

     $('#toc-wrapper').addClass('sidebar-wrapper');

     $('#toc-wrapper').css('width', '230px');
     $('#notebook-container').css('margin-left', '230px');
     $('#toc-wrapper').css('height', '100%');
     $('#toc').css('height', $('#toc-wrapper').height() - $("#toc-header").height());

     setTimeout(function() {
       $('#toc-wrapper').css('top', 0);
     }, 500) //wait a bit
     $('#toc-wrapper').css('left', 0);

   }

   //------------------------------------------------------------------
   // TOC CELL -- if cfg.toc_cell=true, add and update a toc cell in the notebook. 
   //             This cell, initially at the very beginning, can be moved.
   //             Its contents are automatically updated.
   //             Optionnaly, the sections in the toc can be numbered.


   function look_for_cell_toc(callb) { // look for a possible toc cell
     var cells = IPython.notebook.get_cells();
     var lcells = cells.length;
     for (var i = 0; i < lcells; i++) {
       if (cells[i].metadata.toc == "true") {
         cell_toc = cells[i];
         toc_index = i;
         //console.log("Found a cell_toc",i); 
         break;
       }
     }
     callb && callb(i);
   }
   // then process the toc cell:

   function process_cell_toc(cfg, st) {
     // look for a possible toc cell
     var cells = IPython.notebook.get_cells();
     var lcells = cells.length;
     for (var i = 0; i < lcells; i++) {
       if (cells[i].metadata.toc == "true") {
         st.cell_toc = cells[i];
         st.toc_index = i;
         //console.log("Found a cell_toc",i); 
         break;
       }
     }
     //if toc_cell=true, we want a cell_toc. 
     //  If it does not exist, create it at the beginning of the notebook
     //if toc_cell=false, we do not want a cell-toc. 
     //  If one exists, delete it
     if (cfg.toc_cell) {
       if (st.cell_toc == undefined) {
         st.rendering_toc_cell = true;
         //console.log("*********  Toc undefined - Inserting toc_cell");
         st.cell_toc = IPython.notebook.select(0).insert_cell_above("markdown");
         st.cell_toc.metadata.toc = "true";
       }
     } else {
       if (st.cell_toc !== undefined) IPython.notebook.delete_cell(st.toc_index);
       st.rendering_toc_cell = false;
     }
   } //end function process_cell_toc --------------------------

   // Table of Contents =================================================================
   var table_of_contents = function(cfg, st) {

     if (st.rendering_toc_cell) { // if toc_cell is rendering, do not call  table_of_contents,                             
       st.rendering_toc_cell = false; // otherwise it will loop
       return
     }


     var toc_wrapper = $("#toc-wrapper");
     // var toc_index=0;
     if (toc_wrapper.length === 0) {
       create_toc_div(cfg, st);
     }
     var segments = [];
     var ul = $("<ul/>").addClass("toc-item").attr('id', 'toc-level0');

     // update toc element
     $("#toc").empty().append(ul);


     st.cell_toc = undefined;
     // if cfg.toc_cell=true, add and update a toc cell in the notebook. 

     if (liveNotebook) {
       ///look_for_cell_toc(process_cell_toc);        
       process_cell_toc(cfg, st);
     }
     //process_cell_toc();

     var cell_toc_text = "# Table of Contents\n <p>";
     var depth = 1; //var depth = ol_depth(ol);
     var li = ul; //yes, initialize li with ul! 
     var all_headers = $("#notebook").find(":header");
     var min_lvl = 1,
       lbl_ary = [];
     for (; min_lvl <= 6; min_lvl++) {
       if (all_headers.is('h' + min_lvl)) {
         break;
       }
     }
     for (var i = min_lvl; i <= 6; i++) {
       lbl_ary[i - min_lvl] = 0;
     }

     //loop over all headers
     all_headers.each(function(i, h) {
       var level = parseInt(h.tagName.slice(1), 10) - min_lvl + 1;
       // skip below threshold
       if (level > cfg.threshold) {
         return;
       }
       // skip headings with no ID to link to
       if (!h.id) {
         return;
       }
       // skip toc cell if present
       if (h.id == "Table-of-Contents") {
         return;
       }
       //If h had already a number, remove it
       $(h).find(".toc-item-num").remove();
       var num_str = incr_lbl(lbl_ary, level - 1).join('.'); // numbered heading labels
       var num_lbl = $("<span/>").addClass("toc-item-num")
         .text(num_str).append('&nbsp;').append('&nbsp;');

       // walk down levels
       for (var elm = li; depth < level; depth++) {
         var new_ul = $("<ul/>").addClass("toc-item");
         elm.append(new_ul);
         elm = ul = new_ul;
       }
       // walk up levels
       for (; depth > level; depth--) {
         // up twice: the enclosing <ol> and <li> it was inserted in
         ul = ul.parent();
         while (!ul.is('ul')) {
           ul = ul.parent();
         }
       }
       // Change link id -- append current num_str so as to get a kind of unique anchor 
       // A drawback of this approach is that anchors are subject to change and thus external links can fail if toc changes
       // Anyway, one can always add a <a name="myanchor"></a> in the heading and refer to that anchor, eg [link](#myanchor) 
       // This anchor is automatically removed when building toc links. The original id is also preserved and an anchor is created 
       // using it. 
       // Finally a heading line can be linked to by [link](#initialID), or [link](#initialID-num_str) or [link](#myanchor)
       h.id = h.id.replace(/\$/g, '').replace('\\', '')
       if (!$(h).attr("saveid")) {
         $(h).attr("saveid", h.id)
       } //save original id
       h.id = $(h).attr("saveid") + '-' + num_str.replace(/\./g, '');
       // change the id to be "unique" and toc links to it 
       // (and replace '.' with '' in num_str since it poses some pb with jquery)
       var saveid = $(h).attr('saveid')
       //escape special chars: http://stackoverflow.com/questions/3115150/
       var saveid_search = saveid.replace(/[-[\]{}():\/!;&@=$£%§<>%"'*+?.,~\\^$|#\s]/g, "\\$&");
       if ($(h).find("a[name=" + saveid_search + "]").length == 0) { //add an anchor with original id (if it doesnt't already exists)
         $(h).prepend($("<a/>").attr("name", saveid));
       }


       // Create toc entry, append <li> tag to the current <ol>. Prepend numbered-labels to headings.
       li = $("<li/>").append(make_link($(h), num_lbl));

       ul.append(li);
       $(h).prepend(num_lbl);


       //toc_cell:
       if (cfg.toc_cell) {
         var leves = '<div class="lev' + level.toString() + ' toc-item">';
         var lnk = make_link_originalid($(h))
         cell_toc_text += leves + $('<p>').append(lnk).html() + '</div>';
         //workaround for https://github.com/jupyter/notebook/issues/699 as suggested by @jhamrick
         lnk.on('click', function() {
           setTimeout(function() {
             $.ajax()
           }, 100)
         })
       }
     });



     // update navigation menu
     if (cfg.navigate_menu) {
       var pop_nav = function() { //callback for create_nav_menu
         //$('#Navigate_menu').empty().append($("<div/>").attr("id", "navigate_menu").addClass('toc').append(ul.clone().attr('id', 'navigate_menu-level0')))
         $('#navigate_menu').empty().append($('#toc-level0').clone().attr('id', 'navigate_menu-level0'))
       }
       if ($('#Navigate_menu').length == 0) {
         create_navigate_menu(pop_nav);
       } else {
         pop_nav()
       }
     } else { // If navigate_menu is false but the menu already exists, then remove it
       if ($('#Navigate_menu').length > 0) $('#Navigate_sub').remove()
     }



     if (cfg.toc_cell) {
       st.rendering_toc_cell = true;
       //IPython.notebook.to_markdown(toc_index);
       st.cell_toc.set_text(cell_toc_text);
       st.cell_toc.render();
     }

     // Show section numbers if enabled
     cfg.number_sections ? $('.toc-item-num').show() : $('.toc-item-num').hide()

     $(window).resize(function() {
       $('#toc').css({
         maxHeight: $(window).height()
       });
       $('#toc-wrapper').css({
         maxHeight: $(window).height()
       });
       setNotebookWidth(cfg, st);
     });

     $(window).trigger('resize');

   };


   var toggle_toc = function(cfg, st) {
     // toggle draw (first because of first-click behavior)
     //$("#toc-wrapper").toggle({'complete':function(){
     $("#toc-wrapper").toggle({
       'progress': function() {
         setNotebookWidth(cfg, st);
       },
       'complete': function() {
         // recompute:
         st.rendering_toc_cell = false;
         //   table_of_contents(cfg, st);
       }
     });

   };


   $(document).ready(function() {

     var file = documentationDict[$("h1:first").attr("id")];
     var path = "http://vatlab.github.io/sos-docs"
     $("#toc-level0 a").css("color", "#126dce");
     $('a[href="#' + $("h1:first").attr("id") + '"]').hide()
     var docs = documentation;
     var pos = documentation.indexOf(file);

     for (var a = pos; a >= 0; a--) {
       var name = docs[a]
       $('<li><a href="' + path + '/doc/documentation/' + name + '.html">' + name.replace(/_/g, " ") +
         '&nbsp ' + '<i class="fa ' +
         (a === pos ? 'fa-caret-down' : 'fa-caret-right') + '"></i>' + '</a></li>').insertBefore("#toc-level0 li:eq(0)");
     }
     $('a[href="' + path + '/doc/documentation/' + file + '.html' + '"]').css("color", "#126dce");


     for (var a = pos + 1; a < docs.length; a++) {
       var name = docs[a]
       $(".toc #toc-level0").append('<li><a href="' + path + '/doc/documentation/' + name + '.html">' + name.replace(/_/g, " ") +
         '&nbsp' + '<i class="fa fa-caret-right"></i>' + '</a></li>');
     }
   });
</script>
{% endblock footer %}
