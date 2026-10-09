/* Kacheln auf der Startseite ("Nächste Veranstaltungen", "Meine Aufgaben", "Anstehende Verleihe") lassen
 * sich per Drag & Drop am Griff-Symbol in der Kopfzeile verschieben und über die Checkboxen im Menü
 * "Kacheln anpassen" ein-/ausblenden - beides wird pro Benutzerkonto gespeichert (dashboard_kacheln_speichern).
 * Reine Komfortfunktion ohne harte Serverabhängigkeit: schlägt das Speichern fehl (z. B. Netzwerkfehler),
 * bleibt die Änderung nur bis zum nächsten Laden der Seite sichtbar - kein Fehlerdialog nötig. */
(function () {
  function getCookie(name) {
    var wert = null;
    if (document.cookie) {
      document.cookie.split(";").forEach(function (stueck) {
        stueck = stueck.trim();
        if (stueck.indexOf(name + "=") === 0) {
          wert = decodeURIComponent(stueck.substring(name.length + 1));
        }
      });
    }
    return wert;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var container = document.getElementById("dashboard-kacheln");
    if (!container) return;
    var speichernUrl = container.dataset.speichernUrl;

    function kacheln() {
      return Array.from(container.querySelectorAll(".dashboard-kachel"));
    }

    function speichern() {
      var reihenfolge = kacheln()
        .sort(function (a, b) { return parseInt(a.style.order, 10) - parseInt(b.style.order, 10); })
        .map(function (el) { return el.dataset.kachel; });
      var ausgeblendet = kacheln()
        .filter(function (el) { return el.style.display === "none"; })
        .map(function (el) { return el.dataset.kachel; });
      fetch(speichernUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken")},
        body: JSON.stringify({reihenfolge: reihenfolge, ausgeblendet: ausgeblendet}),
      }).catch(function () {});
    }

    // Sichtbarkeit per Checkbox im "Kacheln anpassen"-Menü
    document.querySelectorAll(".kachel-sichtbar-toggle").forEach(function (box) {
      box.addEventListener("change", function () {
        var kachel = container.querySelector('.dashboard-kachel[data-kachel="' + box.value + '"]');
        if (!kachel) return;
        kachel.style.display = box.checked ? "" : "none";
        speichern();
      });
    });

    // Reihenfolge per Drag & Drop am Griff-Symbol (native HTML5-DnD, keine zusaetzliche Bibliothek noetig)
    var ziehendes = null;
    kacheln().forEach(function (kachel) {
      var griff = kachel.querySelector(".kachel-griff");
      if (!griff) return;
      griff.addEventListener("dragstart", function (e) {
        ziehendes = kachel;
        e.dataTransfer.effectAllowed = "move";
      });
    });
    container.addEventListener("dragover", function (e) {
      if (!ziehendes) return;
      e.preventDefault();
      var ziel = e.target.closest(".dashboard-kachel");
      if (!ziel || ziel === ziehendes) return;
      var zielOrder = ziel.style.order;
      ziel.style.order = ziehendes.style.order;
      ziehendes.style.order = zielOrder;
    });
    container.addEventListener("drop", function (e) { e.preventDefault(); });
    container.addEventListener("dragend", function () {
      if (ziehendes) speichern();
      ziehendes = null;
    });
  });
})();
