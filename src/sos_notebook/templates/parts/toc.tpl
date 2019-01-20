{% macro css() %}

<style>

/* The Table of Contents container element */
#toc {
    width: 20%;
    max-height: 90%;
    overflow-y: auto;
    margin-left: 2%;
    margin-top: 60px;
    position: fixed;
    border: 1px solid #ccc;
    webkit-border-radius: 6px;
    moz-border-radius: 6px;
    border-radius: 6px;
}

/* The Table of Contents is composed of multiple nested unordered lists.  These styles remove the default styling of an unordered list because it is ugly. */
#toc ul, #toc li {
    list-style: none;
    margin: 0;
    padding: 0;
    border: none;
    line-height: 1.5em;
}

#toc > .toc-list {
  overflow: hidden;
  position: relative;
  padding-left: 0px;
  text-indent: 0px;

  li {
    list-style: none;
  }
}

.toc-list .toc-list {
  margin: 0;
  text-indent: 15px;
  font-size: 12px;
}


.toc-list .toc-list .toc-list {
  margin: 0;
  text-indent: 30px;
  font-size: 12px;
}

a.toc-link {
  height: 100%;
}

.is-collapsible {
  max-height: 1000px;
  overflow: hidden;
  transition: all 300ms ease-in-out;
}

.is-collapsed {
  max-height: 0;
}

.is-position-fixed {
  position: fixed !important;
  top: 0;
}


/* Twitter Bootstrap Override Style */
.nav-list > li > a, .nav-list .nav-header {
    margin: 0px;
}

/* Twitter Bootstrap Override Style */
.nav-list > li > a {
    padding: 5px;
}

.notebook-container {
  box-shadow: none;
}

li.toc-item .is-active-link {
  background-color: #6197d5;
  color: white;
}

.nav > li > a:hover, .nav > li > a:focus {
    text-decoration: none;
    background-color: #eeeeee;
    color: #337ab7;
}
</style>

<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
{% endmacro %}

{% macro html() %}
{% endmacro %}

{% macro js() %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/tocbot/4.4.2/tocbot.min.js"></script>

<script>
  var content = document.querySelector('.notebook-container')
  var headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6, h7')
  var headingMap = {}

  Array.prototype.forEach.call(headings, function(heading) {
    if (!heading.id) {
      var id = heading.textContent.toLowerCase()
        .split(' ').join('-').split(':').join('')
      headingMap[id] = !isNaN(headingMap[id]) ? headingMap[id]++ : 0
      if (headingMap[id]) {
        heading.id = id + '-' + headingMap[id]
      } else {
        heading.id = id
      }
    }
  })

  tocbot.init({
    // Where to render the table of contents.
    tocSelector: '#toc',
    // Where to grab the headings to build the table of contents.
    contentSelector: '.notebook-container',
    // Which headings to grab inside of the contentSelector element.
    headingSelector: 'h2, h3, h4',
    //
    listClass: 'toc-list',
    extraListClasses: 'nav nav-list',
    //
    listItemClass: 'toc-item',
    //
    activeListItemClass: 'active',
    //
    orderedList: false,
  });
</script>
{% endmacro %}
