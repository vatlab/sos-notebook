
{% macro css() %}

<style type="text/css">

.rendered_html table {
   padding: 0;
   border-collapse: collapse;
   border: none;
 }
.rendered_html thead {
  border: none;
  border-bottom: 1px solid black;
}

.rendered_html table tr {
   border: none;
   background-color: white;
   margin: 0;
   padding: 0;
 }

.rendered_html table tr:nth-child(2n) {
   background-color: #f8f8f8;
}

.rendered_html table tr th {
   font-weight: bold;
   border: none;
   margin: 0;
   padding: 6px 13px;
}

.rendered_html table tr td {
   border: none;
   margin: 0;
   padding: 6px 13px;
}

 .rendered_html tbody tr:hover {
   background-color: #eeeeea;
 }

.rendered_html table tr th :first-child, table tr td :first-child {
   margin-top: 0;
 }

.rendered_html table tr th :last-child, table tr td :last-child {
   margin-bottom: 0;
 }

.sos_hint {
  color: rgba(0,0,0,.4);
  font-family: monospace;
}


.cm-sos-interpolated {
  background-color: #EDD5F3;
}

.cm-sos-sigil {
  background-color: #EDD5F3;
}


pre.section-header.CodeMirror-line {
  background-color: #f7f7f7;
  border-top: 1px solid #ddd;
}
</style>


{% endmacro %}
