{% extends 'full.tpl' %}


{% import 'parts/control_panel.tpl' as control_panel %}

{% block header %}
<meta name="viewport" content="width=device-width, initial-scale=1">
{{ super() }}
{% include 'parts/styles.css' %}
{% include 'parts/code_cell.css' %}
{{ control_panel.css() }}
{% include 'parts/preview.css' %}


{% endblock header %}
{{ macro.killcell() }}

{% block codecell %}
{% if cell['metadata'].get('kernel',none) is not none %}
<div class="lan_{{cell['metadata'].get('kernel', none)}}">
   {{ super() }}
</div>
{% else %}
   {{ super() }}
{% endif %}
{% endblock codecell %}

{%- block input -%}
  {%- if 'scratch' in cell.metadata.tags -%}
	{%- elif 'report_cell' in cell.metadata.tags -%}
        {{ super() }}
  {%- else -%}
        <div class="hidden_content">
        {{ super() }}
        </div>
  {%- endif -%}
{%- endblock input -%}

{% block output %}
  {%- if 'report_output' in cell.metadata.tags -%}
      {{ super() }}
  {%- elif 'report_cell' in cell.metadata.tags -%}
      {{ super() }}
  {%- elif 'scratch' in cell.metadata.tags -%}
  {%- else -%}
      <div class="hidden_content">
      {{ super() }}
      </div>
  {%- endif -%}
{% endblock output %}

{% block markdowncell %}
  {%- if 'hide_output' in cell.metadata.tags -%}
	<div class="hidden_content">
      {{ super() }}
	</div>
  {%- elif 'scratch' in cell.metadata.tags -%}
  {%- else -%}
      {{ super() }}
  {%- endif -%}
{%- endblock markdowncell -%}


{% block body %}
{{ control_panel.html() }}
{{ super() }}
{% endblock body %}

{% block footer %}
{{ control_panel.js() }}
{% include "parts/preview.js" %}
{{ super() }}
{% endblock footer %}
