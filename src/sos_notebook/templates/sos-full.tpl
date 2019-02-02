{% extends 'full.tpl' %}

{% import 'parts/sos_style.tpl' as sos_style %}
{% import 'parts/preview.tpl' as preview %}

{% block html_head %}
<meta name="viewport" content="width=device-width, initial-scale=1">
{{ super().replace('<link rel="stylesheet" href="custom.css">', '') }}
{{ sos_style.css() }}
{{ preview.css() }}

<style>
   {% for item in nb['metadata'].get('sos', {}).get('kernels', []) %}
   {%- if item[2] -%}
   .sos_lan_{{item[0].replace('+', 'plus').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace(' ', '').replace('#', 'sharp')}} .input_prompt {
      background-color: {{item[3]}} !important;
    }
   {%- endif -%}
   {% endfor %}
</style>
{{ preview.js() }}
{% block header_js %}
{% endblock header_js %}
{% endblock html_head %}

{% block codecell %}
{% if cell['metadata'].get('kernel',none) is not none %}
<div class="sos_lan_{{cell['metadata'].get('kernel', none).replace('+', 'plus').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace(' ', '').replace('#', 'sharp')}}">
   {{ super() }}
</div>
{% else %}
   {{ super() }}
{% endif %}
{% endblock codecell %}

{% block body %}
{{ super() }}
{% block footer_js %}
{% endblock footer_js %}
{% endblock body %}
