

{% macro make_toc(topic, nb) %}

<script src="https://vatlab.github.io/sos-docs/js/doc_toc.js"></script>
<script src="https://vatlab.github.io/sos-docs/js/docs.js"></script>
<script>
$(document).ready(function() {
    var cfg = {
        'threshold': {{nb.get('metadata', {}).get('toc', {}).get('threshold', '3') }},
        'number_sections': false,
        'toc_cell': false, // useless here
        'toc_window_display': true, // display the toc window
        "toc_section_display": "block", // display toc contents in the window
        'sideBar': true, // sidebar or floating window
        'navigate_menu': false // navigation menu (only in liveNotebook -- do not change)
    }

    var st = {}; // some variables used in the script
    st.rendering_toc_cell = false;
    st.config_loaded = false;
    st.extension_initialized = false;
    st.nbcontainer_marginleft = $('#notebook-container').css('margin-left')
    st.nbcontainer_marginright = $('#notebook-container').css('margin-right')
    st.nbcontainer_width = $('#notebook-container').css('width')
    st.oldTocHeight = undefined
    st.cell_toc = undefined;
    st.toc_index = 0;

    // fire the main function with these parameters
    table_of_contents(cfg, st);

    var file = {{topic}}Dict[$("h1:first").attr("id")];
    var path = "http://vatlab.github.io/sos-docs"
    $("#toc-level0 a").css("color", "#126dce");
    $('a[href="#' + $("h1:first").attr("id") + '"]').hide()
    var docs = {{topic}};
    var pos = {{topic}}.indexOf(file);

    for (var a = pos; a >= 0; a--) {
        var name = docs[a]
        $('<li><a href="' + path + '/doc/{{topic}}/' + name + '.html">' + name.replace(/_/g, " ") +
            '&nbsp ' + '<i class="fa ' +
            (a === pos ? 'fa-caret-down' : 'fa-caret-right') + '"></i>' + '</a></li>').insertBefore("#toc-level0 li:eq(0)");
    }
    $('a[href="' + path + '/doc/{{topic}}/' + file + '.html' + '"]').css("color", "#126dce");


    for (var a = pos + 1; a < docs.length; a++) {
        var name = docs[a]
        $(".toc #toc-level0").append('<li><a href="' + path + '/doc/{{topic}}/' + name + '.html">' + name.replace(/_/g, " ") +
            '&nbsp' + '<i class="fa fa-caret-right"></i>' + '</a></li>');
    }
});
</script>
{% endmacro %}
