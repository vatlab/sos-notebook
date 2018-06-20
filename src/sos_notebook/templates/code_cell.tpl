
{% block codecell %}
{%- if cell['metadata'].get('kernel',none) is not none -%}
<div class="cell border-box-sizing code_cell rendered lan_{{cell['metadata'].get('kernel', none)}}">
   {{ super() }}
</div>
{% else %}
   {{ super() }}
{% endif %}
{%- endblock codecell %}


{% block header %}
super()

{%- if nb['metadata'].get('sos',{}).get('kernels',none) is not none -%}
<style>  /* defined here in case the main.css below cannot be loaded */
   {% for item in nb['metadata'].get('sos',{}).get('kernels',{}) %}
   {%- if item[2] -%}
   .lan_{{item[0]}} .input_prompt { background-color: {{item[3]}} !important }  
   {%- else -%}
   .lan_{{item[0]}} {}
   {%- endif -%}
   {% endfor %}
</style>
{%- endif -%}

{% endblock header %}
