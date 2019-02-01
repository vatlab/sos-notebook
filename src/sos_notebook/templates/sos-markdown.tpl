
{% extends 'markdown.tpl' %}


{% block input %}
```
{%- if 'kernel' in cell.metadata -%}
    {{ cell.metadata.kernel }}
{%- elif 'magics_language' in cell.metadata  -%}
    {{ cell.metadata.magics_language}}
{%- elif 'name' in nb.metadata.get('language_info', {}) -%}
    {{ nb.metadata.language_info.name }}
{%- endif %}
{{ cell.source}}
```
{% endblock input %}