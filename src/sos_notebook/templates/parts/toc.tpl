{% macro css() %}

<style type="text/css">
{% include 'assets/jquery.tocify.css' %}
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tocbot/4.4.2/tocbot.css">
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
<script src="https://cdnjs.cloudflare.com/ajax/libs/tocbot/4.4.2/tocbot.min.js"></script>

<script>
  tocbot.init({
    // Where to render the table of contents.
    tocSelector: '.tocify',
    // Where to grab the headings to build the table of contents.
    contentSelector: '.notebook-container',
    // Which headings to grab inside of the contentSelector element.
    headingSelector: 'h2, h3, h4',
    //
    listClass: 'tocify-header',
    extraListClasses: 'nav nav-list',
    //
    listItemClass: 'tocify-item',
    //
    activeListItemClass: 'active',
    //
    orderedList: false,
  });
</script>
{% endmacro %}
