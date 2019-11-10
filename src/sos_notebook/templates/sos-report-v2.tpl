{% extends 'sos-full.tpl' %}

{% import 'parts/control_panel.tpl' as control_panel %}

{% block header %}
{{ super() }}
{{ control_panel.css() }}
{% endblock header %}

{%- block input -%}
  {%- if 'jupyter' in cell.metadata and cell.metadata.jupyter.source_hidden -%}
      <div class="hidden_content">
      {{ super() }}
      </div>
	{%- else -%}
      {{ super() }}
  {%- endif -%}
{%- endblock input -%}

{% block output %}
  {%- if 'jupyter' in cell.metadata and cell.metadata.jupyter.outputs_hidden -%}
    <div class="hidden_content">
    {{ super() }}
    </div>
  {%- else -%}
  {{ super() }}
  {%- endif -%}
{% endblock output %}

{% block markdowncell %}
  {%- if 'jupyter' in cell.metadata and cell.metadata.jupyter.source_hidden -%}
    <div class="hidden_content">
        {{ super() }}
    </div>
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
{{ super() }}
{% endblock footer %}
