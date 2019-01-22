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

#display_toggle_dropdown  {
    float: right;
    position: relative;
    z-index: 1000;
    margin-bottom: -25px;
}

.dropbtn {
  background-color: #6c757d;
  border-color: #6c757d;
  border: 1pt solid transparent;
  color: white;
  padding: .375rem .75rem;
  font-size: 14px;
  cursor: pointer;
  border-radius: .25rem;
  transition: color .15s ease-in-out,background-color .15s ease-in-out,border-color .15s ease-in-out,box-shadow .15s ease-in-out;
}

/* The container <div> - needed to position the dropdown content */
.dropdown {
  position: relative;
  display: inline-block;
}

/* Dropdown Content (Hidden by Default) */
.dropdown-content {
  display: none;
  position: absolute;
  background-color: #f9f9f9;
  white-space: nowrap;
  box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.2);
  z-index: 1;
}

/* Links inside the dropdown */
.dropdown-content a {
  color: black;
  padding: .25rem 1.5rem;
  text-decoration: none;
  display: block;
}

/* Change color of dropdown links on hover */
.dropdown-content a:hover {background-color: #f1f1f1}

/* Show the dropdown menu on hover */
.dropdown:hover .dropdown-content {
  display: block;
}

/* Change the background color of the dropdown button when the dropdown content is shown */
.dropdown:hover .dropbtn {
  background-color: #343a40;
}

</style>

{% endmacro %}

{% macro html() %}

<div id='display_toggle_dropdown'>
  <div class="dropdown">
    <button id="showHideButton" class="dropbtn">Report Only &nbsp; <span class="caret"></span></button>
    <div id="showHideMenu" class="dropdown-content">
      <a href="#">Report Only</a>
      <a href="#">Show Code</a>
      <a href="#">Show All</a>
    </div>
  </div>
</div>

{% endmacro %}

{% macro js() %}

<script>

let elem = document.getElementById('display_toggle_dropdown');
elem.parentNode.removeChild(elem);
let container = document.getElementById('notebook-container');
container.insertBefore(elem, container.firstChild);

Array.from(document.querySelectorAll('#showHideMenu a')).forEach(
  function(element, index, array) {
      element.addEventListener("click", showHideToggle);
  });

function setDisplayOfElemenets(names, value = 'none') {
  names.forEach( function(name) {
    Array.from(document.querySelectorAll(name)).forEach(
      function(element, index, array) {
          element.style.display = value;
      });
    });
}

function showHideToggle() {
  var btn = document.getElementById("showHideButton");
  var dropdown = document.getElementById("showHideDropDown");
  // change the CONTENT of the button based on the content of selected option
  btn.innerHTML = this.innerText + ' &nbsp;  <span class="caret"></span>';

  if (this.innerText === "Report Only") {
    setDisplayOfElemenets(['div.input', '.hidden_content', '.output_prompt',
      '.input_prompt', '.output_area prompt', '.output_stderr', '.sos_hint'], 'none');
    Array.from(document.querySelectorAll('div.cell')).forEach(
      function(element, index, array) {
          element.style.padding = '0pt';
          element.style.borderWidth = '0pt';
      }
    );
  } else if (this.innerText === "Show Code") {
    setDisplayOfElemenets(['.div.input'], 'flex');
    setDisplayOfElemenets(['.hidden_content'], 'contents');
    setDisplayOfElemenets(['.output_prompt', '.input_prompt',
      '.output_area .prompt', '.output_stderr', '.sos_hint'], 'none');
    Array.from(document.querySelectorAll('div.cell')).forEach(
      function(element, index, array) {
          element.style.padding = '5pt';
          element.style.borderWidth = '1pt';
      }
    );
  } else if (this.innerText == "Show All") {
    setDisplayOfElemenets(['.div.input'], 'flex');
    setDisplayOfElemenets(['.hidden_content'], 'contents');
    setDisplayOfElemenets(['.output_prompt', '.input_prompt',
     '.output_area .prompt', '.output_stderr', '.sos_hint'], 'block');
    Array.from(document.querySelectorAll('div.cell')).forEach(
      function(element, index, array) {
         element.style.padding = '5pt';
         element.style.borderWidth = '1pt';
     }
   );
  }
}

</script>

{% endmacro %}
