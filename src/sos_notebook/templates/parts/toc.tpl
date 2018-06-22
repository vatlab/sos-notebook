{% macro css() %}

<style type="text/css">
{% include 'assets/jquery.tocify.css' %}
</style>
<style>
#notebook-container {
  box-shadow: none;
}
li.tocify-item.active {
  background-color: #6197d5;
}
.tocify-item.active a {
  color: white;
}

.tocify {
  margin-top: 60px;
}
.tocify ul, .tocify li {
    line-height: 1.5em;
}
.nav > li > a:hover, .nav > li > a:focus {
    text-decoration: none;
    background-color: #eeeeee;
    color: #337ab7;
}
</style>
<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
<link rel="stylesheet" href="https://code.jquery.com/ui/1.9.1/themes/smoothness/jquery-ui.css">
{% endmacro %}

{% macro html() %}
{% endmacro %}

{% macro js() %}
<script
  src="https://code.jquery.com/jquery-1.7.2.min.js"
  integrity="sha256-R7aNzoy2gFrVs+pNJ6+SokH04ppcEqJ0yFLkNGoFALQ="
  crossorigin="anonymous"></script>
<script
  src="https://code.jquery.com/ui/1.9.1/jquery-ui.min.js"
  integrity="sha256-UezNdLBLZaG/YoRcr48I68gr8pb5gyTBM+di5P8p6t8="
  crossorigin="anonymous"></script>
<script>
{% include 'assets/jquery.tocify.min.js' %}
</script>
<script>
    $(function() {
        var toc = $("#toc").tocify({
          selectors: "h2,h3,h4,h5"
        });
    });
</script>
{% endmacro %}
