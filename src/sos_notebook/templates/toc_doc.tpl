{% extends 'sos-cm.tpl' %}

{% import 'parts/doc_toc.tpl' as toc %}

{%- block html_head -%}

{{ super() }}
<link rel="stylesheet" href="https://code.jquery.com/ui/1.11.4/themes/smoothness/jquery-ui.css">
<script type="text/javascript" src="https://ajax.googleapis.com/ajax/libs/jqueryui/1.9.1/jquery-ui.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
<link rel="stylesheet" type="text/css" href="https://vatlab.github.io/sos-docs/css/toc2.css">

{% block toc %}
{{ toc.make_toc('documentation', nb) }}
{% endblock toc %}

{% endblock html_head %}
