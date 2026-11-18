/* Dashboard charts. Colours are read from the active theme variables. */
(function () {
  "use strict";

  var incomeData = document.getElementById("income-expense-data");
  var arrearsData = document.getElementById("arrears-data");
  if (!incomeData || !window.Chart) return;

  var income = JSON.parse(incomeData.textContent || "[]");
  var arrears = JSON.parse((arrearsData && arrearsData.textContent) || "{}");
  var charts = [];

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function palette() {
    return {
      income: css("--chart-income") || css("--ok"),
      expenses: css("--chart-expense") || css("--warn"),
      arrears: css("--status-overdue") || css("--bad"),
      grid: css("--grid-line") || css("--border"),
      text: css("--text-2") || css("--text-1"),
      strong: css("--text-1") || css("--text-2"),
      font: css("--font-sans") || "sans-serif"
    };
  }

  function destroyCharts() {
    charts.forEach(function (chart) {
      chart.destroy();
    });
    charts = [];
  }

  function draw() {
    destroyCharts();
    var colors = palette();
    Chart.defaults.color = colors.text;
    Chart.defaults.font.family = colors.font;
    Chart.defaults.font.size = 12;

    var incomeCanvas = document.getElementById("income-expense-chart");
    if (incomeCanvas) {
      charts.push(new Chart(incomeCanvas, {
        type: "bar",
        data: {
          labels: income.map(function (row) { return row.label; }),
          datasets: [
            {
              label: "Collected",
              data: income.map(function (row) { return row.income; }),
              backgroundColor: colors.income,
              borderRadius: 4
            },
            {
              label: "Expenses",
              data: income.map(function (row) { return row.expenses; }),
              backgroundColor: colors.expenses,
              borderRadius: 4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: colors.text, boxWidth: 12 } }
          },
          scales: {
            x: { grid: { color: colors.grid }, ticks: { color: colors.text } },
            y: {
              beginAtZero: true,
              grid: { color: colors.grid },
              ticks: { color: colors.text }
            }
          }
        }
      }));
    }

    var arrearsCanvas = document.getElementById("arrears-chart");
    if (arrearsCanvas) {
      var labels = Object.keys(arrears);
      charts.push(new Chart(arrearsCanvas, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Overdue balance",
              data: labels.map(function (label) { return Number(arrears[label] || 0); }),
              backgroundColor: colors.arrears,
              borderRadius: 4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: colors.grid }, ticks: { color: colors.text } },
            y: {
              beginAtZero: true,
              grid: { color: colors.grid },
              ticks: { color: colors.text }
            }
          }
        }
      }));
    }
  }

  draw();
  document.addEventListener("themechange", draw);
})();
