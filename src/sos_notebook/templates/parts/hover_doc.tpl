
{% macro html() %}

<div id='sos_hover_tooltip'>
</div>

{% endmacro %}

{% macro css() %}

<style type="text/css">

#sos_hover_tooltip {
  position: fixed;
  display: none;
  background: lightgray;
  border: 1pt solid gray;
  opacity: 50%;
}

.sos_hover_doc:hover {
  cursor: pointer;
}
</style>

{% endmacro %}

{% macro js() %}
<script>

let keyword_links = {
  'input:' : 'https://vatlab.github.io/sos-docs/doc/user_guide/input_output.html',
}

let function_links = {
  'named_output' : 'https://vatlab.github.io/sos-docs/doc/user_guide/named_output.html',
}

function sos_doc_hover_over(evt) {
  let tooltip = document.getElementById('sos_hover_tooltip');
  let tooltiptext = document.getElementById('sos_hover_tooltip');

  let loc = evt.target.getBoundingClientRect();
  tooltip.style.top = loc.y + 'px';
  tooltip.style.left = loc.x + 'px';
  tooltip.style.width = loc.width + 'px';
  tooltip.style.height = loc.height + 'px';

  tooltip.style.display = 'block';
}

function sos_doc_hover_leave(evt) {
  document.getElementById('sos_hover_tooltip').style.display = 'none';
}

function sos_doc_hover_visit(evt) {
  window.open(keyword_links[evt.target.innerText], '_blank')
}


// we wait for 10 seconds before scanning document because we need to
// wait syntax hilighting to be done. A promise is actually needed.
setTimeout(function() {
  // find all keyword in keyword_links
  let elems = document.getElementsByClassName("cm-keyword cm-strong");
  Array.from(elems).filter(elem => elem.innerText in keyword_links).forEach(x => {
    x.classList.add('sos_hover_doc');
    x.addEventListener('mouseover', sos_doc_hover_over);
    x.addEventListener('mouseleave', sos_doc_hover_leave);
    x.addEventListener('click', sos_doc_hover_visit);
  })
}, 5000)

</script>
{% endmacro %}
