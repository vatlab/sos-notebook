
{% extends 'sos-cm-toc.tpl' %}

<!-- {% import 'parts/hover_doc.tpl' as doc %} -->

{% block html_head %}
{{ super() }}
<!-- {{ doc.css() }} -->
{% endblock html_head %}

{% block footer_js %}
{{ super() }}
<!-- {{ doc.js() }} -->
{% endblock footer_js %}
