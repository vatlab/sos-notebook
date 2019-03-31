{% extends 'sos-report.tpl' %}

{% import 'parts/toc.tpl' as toc %}

{% block html_head %}
{{ super() | replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/2.0.3/jquery.min.js"></script>', '') | replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.1.10/require.min.js"></script>', '')}}
{{ toc.css() }}
{% endblock html_head %}

{% block body %}
<body>
  <div class="row-fluid">
    <div class="col-xs-12 col-sm-4 col-md-3">
      <div class="toc-wrapper">
        <div class="toc-header">
        </div>
        <div id="toc" class="toc">
        </div><!--/.well -->
      </div>
    </div><!--/span-->
    <div class="col-xs-12 col-sm-8 col-md-9">
      {{ super() | replace('<body>', '') | replace('</body>', '') | replace('class="container"', 'class="notebook-container"')}}
    </div>
  </div>
</body>
{% endblock body %}

{% block footer_js %}
{{ super() }}
{{ toc.js() }}
{% endblock footer_js %}


{% block markdowncell %}
  {{ super() | replace('&#182;', '')}}
{%- endblock markdowncell -%}
