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

.sos_hover_doc:hover {
  cursor: pointer;
  background: lightgray;  
  opacity: 50%;
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
  let keyword_links = {
  // cm-keyword cm-strong
  'input:' : 'https://vatlab.github.io/sos-docs/doc/user_guide/input_statement.html',
  'output:' : 'https://vatlab.github.io/sos-docs/doc/user_guide/output_statement.html',
  'depends:' : 'https://vatlab.github.io/sos-docs/doc/user_guide/depebds_statement.html',

  // cm-variable cm-sos-option
  'named_output' : 'https://vatlab.github.io/sos-docs/doc/user_guide/named_output.html',
  'output_from' : 'https://vatlab.github.io/sos-docs/doc/user_guide/output_from.html',
  'for_each': 'https://vatlab.github.io/sos-docs/doc/user_guide/for_each.html',
  'trunk_size': 'https://vatlab.github.io/sos-docs/doc/user_guide/trunk_size.html',
  'expand': 'https://vatlab.github.io/sos-docs/doc/user_guide/scripts_in_sos.html#option-expand',

  // cm-builtin cm-strong
  'run:': 'https://vatlab.github.io/sos-docs/doc/user_guide/shell_actions.html',
  'sh:': 'https://vatlab.github.io/sos-docs/doc/user_guide/shell_actions.html',
  'bash': 'https://vatlab.github.io/sos-docs/doc/user_guide/shell_actions.html',
  'R:': 'https://vatlab.github.io/sos-docs/doc/user_guide/script_actions.html',
  'Python:': 'https://vatlab.github.io/sos-docs/doc/user_guide/script_actions.html',

  // cm-meta
  '%sosrun': 'https://vatlab.github.io/sos-docs/doc/user_guide/sos_in_notebook.html#magic-sosrun',
  '%run': 'https://vatlab.github.io/sos-docs/doc/user_guide/sos_in_notebook.html#magic-run',
  '%runfile': 'https://vatlab.github.io/sos-docs/doc/user_guide/sos_in_notebook.html#magic-runfile',
  '%sossave': 'https://vatlab.github.io/sos-docs/doc/user_guide/magic_sossave.html',
  '%preview': 'https://vatlab.github.io/sos-docs/doc/user_guide/magic_preview.html',
}

function visit_sos_doc(evt) {
  window.open(keyword_links[evt.target.innerText], '_blank')
}

// FIXME: we wait for 5 seconds before scanning document because we need to
// wait syntax hilighting to be done. A promise is actually needed.
// setTimeout(function() {
//   let elems = ['cm-keyword cm-strong', 'cm-variable cm-sos-option', 'cm-builtin cm-strong', 'cm-meta'].map(
//     cls => Array.from(document.getElementsByClassName(cls))).reduce((r, a) => r.concat(a), [])
//   Array.from(elems).filter(elem => elem.innerText in keyword_links).forEach(x => {
//     x.classList.add('sos_hover_doc');
//     x.addEventListener('click', visit_sos_doc);
//   })
// }, 5000)





  // function highlight_cells(cells, i, interval) {
  //   setTimeout(function() {
  //     if (! cells[i])
  //       return;
  //     var editor = CodeMirror.fromTextArea(cells[i], {
  //         lineNumbers: false,
  //         styleActiveLine: true,
  //         matchBrackets: true,
  //         readOnly: true,
  //         mode: 'sos',
  //         base_mode: cells[i].name,
  //     });

  //     let select = document.createElement('select');
  //     let option = document.createElement('option');
  //     option.value = cells[i].name;
  //     option.textContent = cells[i].name;
  //     select.appendChild(option);
  //     select.className = "cell-kernel-selector";
  //     select.value = cells[i].name;

  //     cells[i].parentElement.insertBefore(select, cells[i]);

  //     let elems = ['cm-keyword cm-strong', 'cm-variable cm-sos-option', 'cm-builtin cm-strong', 'cm-meta'].map(
  //       cls => Array.from(document.getElementsByClassName(cls))).reduce((r, a) => r.concat(a), [])
  //     Array.from(elems).filter(elem => elem.innerText in keyword_links).forEach(x => {
  //       x.classList.add('sos_hover_doc');
  //       x.addEventListener('click', visit_sos_doc);
  //     })

  //     if (i < cells.length)
  //         highlight_cells(cells, i + 1, interval);
  //   }, interval);
  // }

  // highlight_cells(document.getElementsByClassName("sos-source"), 0, 10);

  function highlight_cell(cell){
    return new Promise((resovle,reject)=>{
        if (! cell)
          resolve("empty");
        var editor = CodeMirror.fromTextArea(cell, {
            lineNumbers: false,
            styleActiveLine: true,
            matchBrackets: true,
            readOnly: true,
            mode: 'sos',
            base_mode: cell.name,
        });

        let select = document.createElement('select');
        let option = document.createElement('option');
        option.value = cell.name;
        option.textContent = cell.name;
        select.appendChild(option);
        select.className = "cell-kernel-selector";
        select.value = cell.name;

        cell.parentElement.insertBefore(select, cell);

        let elems = ['cm-keyword cm-strong', 'cm-variable cm-sos-option', 'cm-builtin cm-strong', 'cm-meta'].map(
          cls => Array.from(document.getElementsByClassName(cls))).reduce((r, a) => r.concat(a), [])
        Array.from(elems).filter(elem => elem.innerText in keyword_links).forEach(x => {
          x.classList.add('sos_hover_doc');
          x.addEventListener('click', visit_sos_doc);
        })
        resovle("done")
    })
  }

  async function highlight_cells(cells){
    for(cell of cells){
      result=await highlight_cell(cell)
    }

  }

  highlight_cells(document.getElementsByClassName("sos-source"))



</script>
{% endmacro %}
