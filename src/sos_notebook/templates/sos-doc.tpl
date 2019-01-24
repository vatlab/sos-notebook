
{% extends 'sos-cm-toc.tpl' %}

{% import 'parts/hover_doc.tpl' as doc %}

{% block html_head %}
{{ super() }}
{{ doc.css() }}
{% endblock html_head %}

{% block footer_js %}
{{ doc.js() }}
{{ super() }}
{% endblock footer_js %}
