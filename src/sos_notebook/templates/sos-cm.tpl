
{% extends 'sos-full.tpl' %}
{% import 'parts/cm.tpl' as cm %}

{%- block html_head -%}

{{ super() | replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.1.10/require.min.js"></script>
', '') }}
{{ cm.css() }}
{%- endblock html_head %}


{% block input %}
{%- if cell['metadata'].get('kernel',none) is not none -%}
<div class="inner_cell" >
  <div class="input_area cm-s-ipython" style="min-height: {{(cell.source.splitlines() | length)*1.21429 + 1.1}}em">
   <textarea rows="{{ cell.source.splitlines() | length }}"
      class="sos-source" name="{{cell['metadata'].get('kernel')}}">{{ cell.source }}</textarea>
  </div>
</div>
{% else %}
   {{ super() }}
{%- endif -%}
{%- endblock input %}

{% block footer_js %}
{{ cm.js() }}
{{ super() }}
{% endblock footer_js %}
