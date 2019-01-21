
{% macro css() %}

<style type="text/css">
.dataframe_container {
   max-height: 400px;
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

.sos_dataframe td, .sos_dataframe th, .sos_dataframe tr {
    white-space: nowrap;
    border: none;
}

.sos_dataframe tr:hover {
    background-color: #e6f2ff;
}
</style>
{% endmacro %}

{% macro js() %}

<script>
function filterDataFrame(id) {
    var input = document.getElementById("search_" + id);
    var filter = input.value.toUpperCase();
    var table = document.getElementById("dataframe_" + id);
    var tr = table.getElementsByTagName("tr");

    // Loop through all table rows, and hide those who don't match the search query
    for (var i = 1; i < tr.length; i++) {
        for (var j = 0; j < tr[i].cells.length; ++j) {
            var matched = false;
            if (tr[i].cells[j].innerHTML.toUpperCase().indexOf(filter) != -1) {
                tr[i].style.display = "";
                matched = true
                break;
            }
            if (!matched)
                tr[i].style.display = "none";
        }
    }
}

function sortDataFrame(id, n, dtype) {
    var table = document.getElementById("dataframe_" + id);

    var tb = table.tBodies[0]; // use `<tbody>` to ignore `<thead>` and `<tfoot>` rows
    var tr = Array.prototype.slice.call(tb.rows, 0); // put rows into array

    if (dtype === 'numeric') {
        var fn = function(a, b) {
            return parseFloat(a.cells[n].textContent) <= parseFloat(b.cells[n].textContent) ? -1 : 1;
        }
    } else {
        var fn = function(a, b) {
            var c = a.cells[n].textContent.trim().localeCompare(b.cells[n].textContent.trim());
            return c > 0 ? 1 : (c < 0 ? -1 : 0) }
    }
    var isSorted = function(array, fn) {
        if (array.length < 2)
            return 1;
        var direction = fn(array[0], array[1]);
        for (var i = 1; i < array.length - 1; ++i) {
            var d = fn(array[i], array[i+1]);
            if (d == 0)
                continue;
            else if (direction == 0)
                direction = d;
            else if (direction != d)
                return 0;
            }
        return direction;
    }

    var sorted = isSorted(tr, fn);

    if (sorted == 1 || sorted == -1) {
        // if sorted already, reverse it
        for(var i = tr.length - 1; i >= 0; --i)
            tb.appendChild(tr[i]); // append each row in order
    } else {
        tr = tr.sort(fn);
        for(var i = 0; i < tr.length; ++i)
            tb.appendChild(tr[i]); // append each row in order
    }
}

</script>

{% endmacro %}
