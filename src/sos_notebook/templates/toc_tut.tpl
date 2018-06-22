{% extends 'toc_doc.tpl' %}


{%- block toc -%}
{{ toc.make_toc('tutorials', nb) }}
{% endblock toc %}
