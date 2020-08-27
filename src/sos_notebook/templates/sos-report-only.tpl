{% extends 'sos-cm.tpl' %}

{%- block codecell -%}
  {%- if 'scratch' in cell.metadata.tags -%}
  {%- elif 'jupyter' in cell.metadata and cell.metadata.jupyter.source_hidden and (not cell.outputs or cell.metadata.jupyter.outputs_hidden) -%}
  {%- else -%}
  {{ super() }}
  {%- endif -%}
{%- endblock codecell -%}


{%- block in_prompt -%}
{%- endblock in_prompt -%}

{%- block input -%}
  {%- if 'scratch' in cell.metadata.tags -%}
  {%- elif 'jupyter' in cell.metadata and cell.metadata.jupyter.source_hidden and (not cell.outputs or cell.metadata.jupyter.source_hidden) -%}
	{%- else -%}
      {{ super() }}
  {%- endif -%}
{%- endblock input -%}

{#
  output_prompt doesn't do anything in HTML,
  because there is a prompt div in each output area (see output block)
#}
{% block output_area_prompt %}
{% endblock output_area_prompt %}

{% block output %}
  {%- if 'scratch' in cell.metadata.tags -%}
  {%- elif 'jupyter' in cell.metadata and cell.metadata.jupyter.outputs_hidden -%}
  {%- else -%}
  {{ super() }}
  {%- endif -%}
{% endblock output %}

{# remove stderr #}
{% block stream_stderr -%}
{%- endblock stream_stderr %}


{% block markdowncell %}
  {%- if 'scratch' in cell.metadata.tags -%}
  {%- elif 'jupyter' in cell.metadata and cell.metadata.jupyter.source_hidden -%}
  {%- else -%}
      <div class="cell border-box-sizing text_cell rendered{{ celltags(cell) }}">
      <div class="inner_cell">
      <div class="text_cell_render border-box-sizing rendered_html">
      {{ cell.source  | markdown2html | strip_files_prefix }}
      </div>
      </div>
      </div>

  {%- endif -%}
{%- endblock markdowncell -%}
