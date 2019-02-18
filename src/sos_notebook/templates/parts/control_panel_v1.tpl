{% macro css() %}
<style type="text/css">

.output_stderr {
    display: none;
}

.hidden_content {
    display: none;
}

.input_prompt {
    display: none;
}

.output_area .prompt {
    display: none;
}

.output_prompt {
    display: none;
}

.display_control_panel  {
    padding: 10pt;
    left: 5px;
    top: 5px;
    position: fixed;
    z-index: 1000;
}
.display_control_panel:hover {
    background: rgb(224, 234, 241);
}
.display_checkboxes {
    margin-top: 5pt;
}
.display_control_panel:hover .display_control {
    display: block;
    opacity: 100;
}
.display_control_panel .display_control {
    opacity: 0;
}

</style>

{% endmacro %}

{% macro html() %}

<div class='display_control_panel'>
   <div class="display_control">
      Display content:<br>
      <div class="display_checkboxes">
         <input type="checkbox" id="show_cells" name="show_cells" onclick="toggle_source()">
         <label for="show_cells">All cells</label>
         <br>
         <input type="checkbox" id="show_prompt" name="show_prompt" onclick="toggle_prompt()">
         <label for="show_prompt">Prompt</label>
         <br>
         <input type="checkbox" id="show_messages" name="show_messages" onclick="toggle_messages()">
         <label for="show_messages">Messages</label>
      </div>
   </div>
</div>

{% endmacro %}

{% macro js() %}

<script>
function toggle_source() {
    var btn = document.getElementById("show_cells");
    if (btn.checked) {
        $('div.input').css('display', 'flex');
        $('.hidden_content').show();
        // this somehow does not work.
        $('div.cell').css('padding', '5pt').css('border-width', '1pt');
    } else {
        $('div.input').hide();
        $('.hidden_content').hide();
        $('div.cell').css('padding', '0pt').css('border-width', '0pt');
    }
}
function toggle_prompt() {
    var btn = document.getElementById("show_prompt");
    if (btn.checked) {
        $('.output_prompt').show();
        $('.input_prompt').show();
        $('.output_area .prompt').show();
    } else {
        $('.output_prompt').hide();
        $('.input_prompt').hide();
        $('.output_area .prompt').hide();
    }
}
function toggle_messages() {
    var btn = document.getElementById("show_messages");
    if (btn.checked) {
        $('.sos_hint').show();
        $('.output_stderr').show();
    } else {
        $('.output_stderr').hide();
        $('.sos_hint').hide();
    }
}

</script>

{% endmacro %}
