
{% macro css() %}


<link href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.42.2/codemirror.css" rel="stylesheet">


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

.rendered_html table tr th :first-child,
table tr td :first-child {
	margin-top: 0;
}

.rendered_html table tr th :last-child,
table tr td :last-child {
	margin-bottom: 0;
}

.output_area .run_this_cell {
	padding-bottom: 0px;
	padding-top: 0px;
}

div.output_subarea:empty {
	padding: 0px;
}

/* the cell_kernel_selector will be absolute to the parent
*  of absolute or relative position, so putting div.input_area
* as relative will prevent the select from going out of the
* input cell */
div.input_area {
	position: relative;
}

.code_cell .cell_kernel_selector {
	/* width:70pt; */
	background: none;
	z-index: 1000;
	position: absolute;
	height: 1.7em;
	margin-top: 3pt;
	right: 8pt;
	font-size: 80%;
}

.sos_logging {
	font-family: monospace;
	margin: -0.4em;
	padding-left: 0.4em;
}

.sos_hint {
	color: rgba(0, 0, 0, .4);
	font-family: monospace;
}

.sos_debug {
	color: blue;
}

.sos_trace {
	color: darkcyan;
}

.sos_hilight {
	color: green;
}

.sos_info {
	color: black;
}

.sos_warning {
	color: black;
	background: #fdd
}

.sos_error {
	color: black;
	background: #fdd
}

.text_cell .cell_kernel_selector {
	display: none;
}

.session_info td {
	text-align: left;
}

.session_info th {
	text-align: left;
}

.session_section {
	text-align: left;
	font-weight: bold;
	font-size: 120%;
}

.report_output {
	border-right-width: 13px;
	border-right-color: #aaaaaa;
	border-right-style: solid;
	/*   box-shadow: 13px 0px 0px #aaaaaa; */
}

.one_liner {
	overflow: hidden;
	height: 15px;
}

.one_liner:hover {
	height: auto;
	width: auto;
}

.dataframe_container {
	max-height: 400px
}

.dataframe_input {
	border: 1px solid #ddd;
	margin-bottom: 5px;
}

.scatterplot_by_rowname div.xAxis div.tickLabel {
	transform: translateY(15px) translateX(15px) rotate(45deg);
	-ms-transform: translateY(15px) translateX(15px) rotate(45deg);
	-moz-transform: translateY(15px) translateX(15px) rotate(45deg);
	-webkit-transform: translateY(15px) translateX(15px) rotate(45deg);
	-o-transform: translateY(15px) translateX(15px) rotate(45deg);
	/*rotation-point:50% 50%;*/
	/*rotation:270deg;*/
}

.sos_dataframe td,
.sos_dataframe th {
	white-space: nowrap;
}

.toc-item-highlight-select {
	background-color: Gold
}

.toc-item-highlight-execute {
	background-color: red
}

.lev1 {
	margin-left: 5px
}

.lev2 {
	margin-left: 10px
}

.lev3 {
	margin-left: 10px
}

.lev4 {
	margin-left: 10px
}

.lev5 {
	margin-left: 10px
}

.lev6 {
	margin-left: 10px
}

.lev7 {
	margin-left: 10px
}

.lev8 {
	margin-left: 10px
}

time.pending,
time.submitted,
time.running,
table.workflow_table,
table.task_table {
	border: 0px;
}

table.workflow_table i,
table.task_table i {
	margin-right: 5px;
}

td.workflow_name {
	width: 10em;
	text-align: left;
}

td.workflow_name pre,
td.task_name pre {
	font-size: 1.2em;
}

td.workflow_id,
td.task_id {
	width: 15em;
	text-align: left;
}

td.task_tags {
	text-align: left;
	max-width: 33em;
}

td.task_id {
	text-align: left;
}

td.task_id span,
td.task_tags span {
	display: inline-flex;
}

td.task_tags span pre {
	padding-right: 0.5em;
}

td.task_tags i {
	margin-right: 0px;
}

.task_id_actions,
.task_tag_actions {
	display: none;
}

.task_id_actions .fa:hover,
.task_tag_actions .fa:hover {
	color: blue;
}

.task_id:hover .task_id_actions,
.task_tags:hover .task_tag_actions {
	display: flex;
	flex-direction: row;
}

td.workflow_index {
	width: 5em;
	text-align: left;
}

td.workflow_status {
	width: 20em;
	text-align: left;
}

td.task_timer {
	width: 15em;
	text-align: left;
}

td.task_timer pre {
	text-overflow: ellipsis;
	overflow: hidden;
	white-space: nowrap;
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
	/* text-transform: uppercase; */
	font-family: monospace;
}

table.task_table span {
	/* text-transform: uppercase; */
	font-family: monospace;
}

table.workflow_table.pending pre,
table.task_table.pending pre,
table.task_table.submitted pre,
table.task_table.missing pre {
	color: #9d9d9d;
	/* gray */
}

table.workflow_table.running pre,
table.task_table.running pre {
	color: #cdb62c;
	/* yellow */
}

table.workflow_table.completed pre,
table.task_table.completed pre {
	color: #39aa56;
	/* green */
}

table.workflow_table.aborted pre,
table.task_table.aborted pre {
	color: #FFA07A;
	/* salmon */
}

table.workflow_table.failed pre,
table.task_table.failed pre {
	color: #db4545;
	/* red */
}

table.task_table {
	border: 0px;
	border-style: solid;
}

.code_cell .cm-header-1,
.code_cell .cm-header-2,
.code_cell .cm-header-3,
.code_cell .cm-header-4,
.code_cell .cm-header-5,
.code_cell .cm-header-6 {
	font-size: 100%;
	font-style: normal;
	font-weight: normal;
	font-family: monospace;
}

.task_hover {
	color: black !important;
}


/* side panel */

#panel-wrapper #panel div.output_area {
	display: -webkit-box;
}

#panel-wrapper #panel div.output_subarea {
	max_width: 100%;
}

#panel-wrapper #panel .output_scroll {
	height: auto;
}

.anchor-cell {
	bottom: 5px;
	margin-right: 5px;
	flex: 0 0 auto;
	margin-top: 2em !important;
}

.cm-sos-interpolated {
	background-color: rgb(223, 144, 207, 0.4);
}

.cm-sos-sigil {
	background-color: rgb(223, 144, 207, 0.4);
}


/*
.cm-sos-script {
font-style: normal;
}

.cm-sos-option {
font-style: italic;
} */

.panel-icons li:hover {
	color: green;
}

.bs-callout {
    padding: 20px;
    margin: 20px 0;
    border: 1px solid #eee;
    border-left-width: 5px;
    border-radius: 3px;
}
.bs-callout h4 {
    margin-top: 0 !important;
    margin-bottom: 5px;
    font-weight: 500;
    line-height: 1.1;
    display: block;
    margin-block-start: 1.33em;
    margin-block-end: 1.33em;
    margin-inline-start: 0px;
    margin-inline-end: 0px;
}
.bs-callout p:last-child {
    margin-bottom: 0;
}
.bs-callout code {
    border-radius: 3px;
}
.bs-callout+.bs-callout {
    margin-top: -5px;
}
.bs-callout-default {
    border-left-color: #777;
}
.bs-callout-default h4 {
    color: #777;
}
.bs-callout-primary {
    border-left-color: #428bca;
}
.bs-callout-primary h4 {
    color: #428bca;
}
.bs-callout-success {
    border-left-color: #5cb85c;
}
.bs-callout-success h4 {
    color: #5cb85c;
}
.bs-callout-danger {
    border-left-color: #d9534f;
}
.bs-callout-danger h4 {
    color: #d9534f;
}
.bs-callout-warning {
    border-left-color: #f0ad4e;
}
.bs-callout-warning h4 {
    color: #f0ad4e;
}
.bs-callout-info {
    border-left-color: #5bc0de;
}
.bs-callout-info h4 {
    color: #5bc0de;
}

</style>



{% endmacro %}
