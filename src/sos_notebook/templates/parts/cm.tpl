{% macro css() %}

<link type="text/css" rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/codemirror.css">

<style type="text/css">

.inner_cell .CodeMirror {
    height: auto;
}

.cell-kernel-selector {
  width:70pt;
  background: none;
  z-index: 1000;
  position: absolute;
  height: 1.7em;
  margin-top: 3pt;
  right: 8pt;
  font-size: 80%;
}
textarea.sos-source {
  line-height: 1.21429em;
  font-size: 14px;
  background: none;
  width: 100%;
  border: none;
  font-family: monospace;
  height: auto;
  padding: 4px;
  outline: none;
  position: relative;
  resize: none;
  overflow: hidden;
  vertical-align: text-top;
}
</style>

{% endmacro %}

{% macro js() %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/codemirror.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/python/python.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/r/r.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/octave/octave.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/ruby/ruby.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/sas/sas.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/javascript/javascript.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/shell/shell.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/julia/julia.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.38.0/mode/markdown/markdown.js"></script>
<script>
    {% include 'sos-mode.js' %}
</script>
<script>
    function highlight_cells(cells, i, interval) {
        setTimeout(function() {
            var editor = CodeMirror.fromTextArea(cells[i], {
                lineNumbers: false,
                styleActiveLine: true,
                matchBrackets: true,
                readOnly: true,
                mode: 'sos',
                base_mode: cells[i].name,
            });
            $(cells[i]).parent().prepend("<select class='cell-kernel-selector'><option>"
					       + cells[i].name + "</option></select>");
            if (i < cells.length)
                highlight_cells(cells, i + 1, interval);
        }, interval);
    }

    highlight_cells(document.getElementsByClassName("sos-source"), 0, 10);
</script>
{% endmacro %}
