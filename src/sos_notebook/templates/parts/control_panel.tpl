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
    right: 25px;
    top: 25px;
    position: absolute;
    z-index: 1000;
}

</style>

{% endmacro %}

{% macro html() %}

<div class='display_control_panel'>
  <div class="dropdown">
    <button id="showHideButton" class="btn btn-primary dropdown-toggle" type="button" data-toggle="dropdown">Report Only &nbsp; <span class="caret"></span></button>
    <ul id="showHideMenu" class="dropdown-menu">
      <li><a href="#">Report Only</a></li>
      <li><a href="#">Show Code</a></li>
      <li><a href="#">Show All</a></li>
    </ul>
  </div>
</div>

{% endmacro %}

{% macro js() %}

<script
  src="https://code.jquery.com/jquery-3.3.1.min.js"
  integrity="sha256-FgpCb/KJQlLNfOu91ta32o/NMZxltwRo8QtmkMRdAu8="
  crossorigin="anonymous"></script>

<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.4.0/js/bootstrap.min.js"></script>

<script>


<script
  src="https://code.jquery.com/jquery-3.3.1.min.js"
  integrity="sha256-FgpCb/KJQlLNfOu91ta32o/NMZxltwRo8QtmkMRdAu8="
  crossorigin="anonymous"></script>
$(document).ready(function() {
  $(".display_control_panel").detach().appendTo("#notebook-container");
  $('#showHideMenu a').on('click', showHideToggle);
})

function showHideToggle() {
  var btn = document.getElementById("showHideButton");
  var dropdown = document.getElementById("showHideDropDown");
  // change the CONTENT of the button based on the content of selected option
  btn.innerHTML = this.innerText + ' &nbsp;  <span class="caret"></span>';

  if (this.innerText === "Report Only") {
    $('div.input').hide();
    $('.hidden_content').hide();
    $('div.cell').css('padding', '0pt').css('border-width', '0pt');

    $('.output_prompt').hide();
    $('.input_prompt').hide();
    $('.output_area .prompt').hide();

    $('.output_stderr').hide();
    $('.sos_hint').hide();
  } else if (this.innerText === "Show Code") {
    $('div.input').css('display', 'reset');
    $('.hidden_content').css('display', 'contents');
    // this somehow does not work.
    $('div.cell').css('padding', '5pt').css('border-width', '1pt');

    $('.output_prompt').hide();
    $('.input_prompt').hide();
    $('.output_area .prompt').hide();

    $('.output_stderr').hide();
    $('.sos_hint').hide();

  } else if (this.innerText == "Show All") {
    $('div.input').css('display', 'reset');
    $('.hidden_content').css('display', 'contents');
    // this somehow does not work.
    $('div.cell').css('padding', '5pt').css('border-width', '1pt');

    $('.output_prompt').show();
    $('.input_prompt').show();
    $('.output_area .prompt').show();

    $('.sos_hint').show();
    $('.output_stderr').show();
  }
}

</script>

{% endmacro %}
