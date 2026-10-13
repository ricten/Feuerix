// Formatierter Text (TinyMCE, lokal ausgeliefert - kein CDN) fuer Vorlagen, Schriftstuecke und Serienbriefe.
// Erlaubt bewusst nur Formatierungen, die auch im PDF/Word/E-Mail ankommen (siehe apps/documents/richtext.py).
(function () {
  if (!window.tinymce) return;
  var felder = document.querySelectorAll("textarea.tinymce-editor");
  if (!felder.length) return;

  function platzhalter(ta) {
    try { return JSON.parse(ta.getAttribute("data-platzhalter") || "[]"); } catch (e) { return []; }
  }

  var basis = "/static/vendor/tinymce";
  window.tinymce.init({
    selector: "textarea.tinymce-editor",
    license_key: "gpl",
    base_url: basis,
    suffix: ".min",
    language: "de",
    language_url: basis + "/langs/de.js",
    menubar: false,
    branding: false,
    promotion: false,
    statusbar: false,
    height: 480,
    plugins: "lists table link autolink charmap",
    toolbar: "undo redo | blocks | bold italic underline | alignleft aligncenter alignright alignjustify | " +
             "bullist numlist outdent indent | table link charmap | platzhalter | removeformat",
    block_formats: "Absatz=p; Überschrift 1=h1; Überschrift 2=h2; Überschrift 3=h3",
    table_toolbar: "tableprops tabledelete | tableinsertrowbefore tableinsertrowafter tabledeleterow | " +
                   "tableinsertcolbefore tableinsertcolafter tabledeletecol",
    table_appearance_options: false,
    table_advtab: false, table_cell_advtab: false, table_row_advtab: false,
    link_title: false, link_target_list: false, link_assume_external_targets: "https",
    entity_encoding: "raw",
    convert_urls: false,
    paste_as_text: false,
    valid_elements: "p[style],br,strong/b,em/i,u,s/strike,h1[style],h2[style],h3[style],ul,ol,li[style]," +
                    "table,thead,tbody,tfoot,tr,th[style|colspan|rowspan],td[style|colspan|rowspan],a[href]",
    valid_styles: { "*": "text-align" },
    content_style: "body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; max-width: 17cm; margin: 1rem auto; } " +
                   "table { border-collapse: collapse; } td, th { border: 1px solid #999; padding: 4px 6px; }",
    setup: function (editor) {
      var liste = platzhalter(editor.getElement());
      editor.ui.registry.addMenuButton("platzhalter", {
        text: "{ } Platzhalter",
        tooltip: "Platzhalter einfügen (werden beim Erzeugen durch Daten ersetzt)",
        fetch: function (callback) {
          callback(liste.map(function (gruppe) {
            return {
              type: "nestedmenuitem", text: gruppe[0],
              getSubmenuItems: function () {
                return gruppe[1].map(function (p) {
                  return {
                    type: "menuitem", text: "{" + p[0] + "} – " + p[1],
                    onAction: function () { editor.insertContent("{" + p[0] + "}"); }
                  };
                });
              }
            };
          }));
        }
      });
      // beim Absenden den Inhalt in das Formularfeld uebernehmen
      editor.on("submit", function () { editor.save(); });
    }
  });
})();
