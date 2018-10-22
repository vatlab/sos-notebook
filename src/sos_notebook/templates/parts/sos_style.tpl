
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
  box-sizing: border-box;
  -moz-box-sizing: border-box;
  -webkit-box-sizing: border-box;
  background-color: #f7f7f7;
  /* border-top: 1px solid #ddd; */
}

.code_cell .cm-header-1,
.code_cell .cm-header-2,
.code_cell .cm-header-3,
.code_cell .cm-header-4,
.code_cell .cm-header-5,
.code_cell .cm-header-6
{
    font-size: 100%;
    font-style: normal;
    font-weight: normal;
    font-family: monospace;
}



div.cell {
  /* Old browsers */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-box-align: stretch;
  display: -moz-box;
  -moz-box-orient: vertical;
  -moz-box-align: stretch;
  display: box;
  box-orient: vertical;
  box-align: stretch;
  /* Modern browsers */
  display: flex;
  flex-direction: column;
  align-items: stretch;
  border-radius: 2px;
  box-sizing: border-box;
  -moz-box-sizing: border-box;
  -webkit-box-sizing: border-box;
  border-width: 1px;
  border-style: solid;
  border-color: transparent;
  width: 100%;
  padding: 5px;
  /* This acts as a spacer between cells, that is outside the border */
  margin: 0px;
  outline: none;
  position: relative;
  overflow: visible;
}



table.workflow_table,
table.task_table {
  border: 0px;
}

table.workflow_table i,
table.task_table i  {
  margin-right: 5px;
}

td.workflow_name
{
  width: 10em;
  text-align: left;
}

td.workflow_name pre,
td.task_name pre {
  font-size: 1.2em;
}

td.workflow_id,
td.task_id
{
  width: 15em;
  text-align: left;
}

td.workflow_index
{
  width: 5em;
  text-align: left;
}

td.workflow_status,
td.task_timer
{
  width: 20em;
  text-align: left;
}

td.task_icon {
    font-size: 0.75em;
}

td.task_status,
{
  width: 15em;
  text-align: left;
}

table.workflow_table span {
  text-transform: uppercase;
  font-family: monospace;
}

table.task_table span {
  text-transform: uppercase;
  font-family: monospace;
}

table.workflow_table.pending pre,
table.task_table.pending pre,
table.task_table.submitted pre,
table.task_table.missing pre {
  color: #9d9d9d; /* gray */
}

table.workflow_table.running pre,
table.task_table.running pre {
  color: #cdb62c; /* yellow */
}

table.workflow_table.completed pre,
table.task_table.completed pre {
  color: #39aa56; /* green */
}

table.workflow_table.aborted pre,
table.task_table.aborted pre {
  color: #FFA07A; /* salmon */
}

table.workflow_table.failed pre,
table.task_table.failed pre {
  color: #db4545; /* red */
}

table.task_table {
  border: 0px;
  border-style: solid;
}

</style>



{% endmacro %}
