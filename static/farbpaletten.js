/* Zeigt unter jedem Farbfeld (type="color", z. B. die Akzentfarbe in den Vereinseinstellungen) eine Reihe
 * gaengiger Feuerwehr-Farben zur Auswahl per Klick - das Farbfeld selbst bleibt frei editierbar, die Paletten
 * sind nur eine Erleichterung. */
(function () {
  var PALETTE = [
    ["#AF2B1E", "Feuerwehrrot (RAL 3000)"],
    ["#CC0605", "Verkehrsrot (RAL 3020)"],
    ["#1C1C1C", "Schwarz"],
    ["#36393F", "Anthrazit"],
    ["#F7FA00", "Leuchtgelb (RAL 1026)"],
    ["#1F4E79", "Dunkelblau"],
  ];

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('input[type="color"]').forEach(function (feld) {
      var reihe = document.createElement("div");
      reihe.className = "farbpaletten-reihe";
      PALETTE.forEach(function (eintrag) {
        var farbe = eintrag[0], name = eintrag[1];
        var swatch = document.createElement("button");
        swatch.type = "button";
        swatch.className = "farbpaletten-swatch";
        swatch.style.backgroundColor = farbe;
        swatch.title = name;
        swatch.setAttribute("aria-label", name);
        swatch.addEventListener("click", function () {
          feld.value = farbe;
          feld.dispatchEvent(new Event("input", {bubbles: true}));
          feld.dispatchEvent(new Event("change", {bubbles: true}));
        });
        reihe.appendChild(swatch);
      });
      feld.insertAdjacentElement("afterend", reihe);
    });
  });
})();
