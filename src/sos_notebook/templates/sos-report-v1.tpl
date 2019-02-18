{% extends 'sos-full.tpl' %}

{% import 'parts/control_panel_v1.tpl' as control_panel %}

{% block header %}
{{ super() }}
{{ control_panel.css() }}
{% endblock header %}

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
{{ super() }}
{% endblock footer %}
