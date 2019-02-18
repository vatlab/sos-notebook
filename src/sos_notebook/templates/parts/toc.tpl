{% macro css() %}

<style>

/* The Table of Contents container element */
.toc-wrapper {
    flex-flow: column;
    display: flex;

    width: 20%;
    max-height: calc(100% - 120px);
    margin-left: 2%;
    margin-top: 60px;
    position: fixed;
    border: 1px solid #ccc;
    webkit-border-radius: 6px;
    moz-border-radius: 6px;
    border-radius: 6px;
}

.toc-header {
  flex: 0 1 auto;
}

/* The Table of Contents is composed of multiple nested unordered lists.  These styles remove the default styling of an unordered list because it is ugly. */
#toc {
      overflow-y: auto;
      flex: 1 1 auto;
}

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

  li {
    list-style: none;
  }
}

#toc > .toc-list  a {
  margin: 0;
  padding-left: 10px;
}

#toc > .toc-list .toc-list a {
  margin: 0;
  padding-left: 25px;
  font-size: 12px;
}


#toc > .toc-list .toc-list .toc-list a {
  margin: 0;
  padding-left: 40px;
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

#notebook-container {
  box-shadow: none;
}

/* https://github.com/tscanlin/tocbot/issues/121 */
h1:focus, h2:focus, h3:focus, h4:focus, h5:focus, h6:focus, h7:focus {
  outline: none !important;
  box-shadow: none !important;
}

</style>

<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
{% endmacro %}

{% macro html() %}
{% endmacro %}

{% macro js() %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/tocbot/4.4.2/tocbot.min.js"></script>

<script>

  function fixIDsForToc(headings = null) {
    let headingMap = {}

    if (!headings) {
      let content = document.querySelector('.notebook-container')
      headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6, h7')
    }
    Array.prototype.forEach.call(headings, function(heading) {
      var id = heading.id ? heading.id : heading.textContent.toLowerCase();
      id = id.split(' ').join('-').replace(/["'\!\@\#\$\%\^\&\*\(\)\:]/ig, '');
      headingMap[id] = !isNaN(headingMap[id]) ? ++headingMap[id] : 0;
      if (headingMap[id]) {
        heading.id = id + '-' + headingMap[id]
      } else {
        heading.id = id
      }
    })
  }


  function indexedHeaders(headings) {
      if (!headings) {
          return '';
      }
      let counts = [0, 0, 0, 0, 0, 0, 0]
      for (let i = 0; i < headings.length; ++i) {
        ++counts[parseInt(headings[i].tagName[1])-1]
      }
      // now, we remove the first 1 if it is the first tag, and if
      // it has only one, and if it is not the only header
      let first = counts.findIndex(x => x > 0);
      if (counts[first] == 1 && counts.reduce((a, b) => a + b, 0) != counts[first]
         && parseInt(headings[0].tagName[1]) === first + 1) {
          counts[first] = 0;
      }
      //
      return counts.map((x, idx) => x > 0 ? 'H' + (idx+1) : '').filter(x => x).join(',');
  }


  function updateTOC ( ) {
    var content = document.querySelector('.notebook-container')
    var headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6, h7')

    fixIDsForToc(headings);

    tocbot.init({
      // Where to render the table of contents.
      tocSelector: '#toc',
      // Where to grab the headings to build the table of contents.
      contentSelector: '.notebook-container',
      // Which headings to grab inside of the contentSelector element.
      headingSelector: indexedHeaders(headings),
      //
      listClass: 'toc-list',
      extraListClasses: 'nav nav-list',
      //
      listItemClass: 'toc-item',
      //
      activeListItemClass: 'active',
      //
      orderedList: false,
      //
      scrollSmooth: true
    });
  }

  updateTOC()

</script>
{% endmacro %}
