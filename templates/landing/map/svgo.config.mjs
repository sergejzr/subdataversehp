// Landing-only derivative of templates/assets/pagedata/DP.svg (the source
// stays untouched; the old page still inlines it). SVGO is a local dev tool,
// not a server dependency. Regenerate from the subdataversehp root:
// $ npx --yes svgo@4.1.0 --config templates/landing/map/svgo.config.mjs -i templates/assets/pagedata/DP.svg -o templates/landing/map/DP.landing.svg && sha256sum templates/assets/pagedata/DP.svg | cut -d' ' -f1 > templates/landing/map/DP.landing.svg.sha256
//
// landing.py checks DP.landing.svg.sha256 against DP.svg at build time and
// skips the preview with [LANDING] ERROR when the derivative is stale.
//
// Contract (landing.py, landing.css): nothing that renders or is referenced
// goes. Every rendered id and class, every element type, viewBox, title/desc,
// role and aria-* survive. landing.py finds partners by
// inkscape:label="rect_<label>" / "text_<label>", so those labels are kept;
// all other editor data goes. display:none subtrees (Illustrator leftovers,
// 463 kB) go; DESIGN-NOTES.md records the checks that none of them is
// referenced or shown by landing.css. Only lossless path rewrites; the
// precision is the lowest without visible change at 1440 and 375 px.

// Geometry (path d, polygon/polyline points) in user units. The map is drawn
// at 1771 user units and shown at most ~1400 px wide, so 1 unit < 1 px.
const GEOMETRY_PRECISION = 1;

const PARTNER_LABEL = /^(rect|text)_/;
// ns1 is Illustrator's &ns_ai; namespace, mangled into an invalid URI.
const EDITOR_PREFIXES = ['sodipodi', 'inkscape', 'ns1'];

const isEditorName = (name) => name.includes(':') && EDITOR_PREFIXES.includes(name.split(':')[0]);

// Editor elements keep only their id (sodipodi:namedview), editor attributes
// go except the partner labels; removeUnusedNS then drops unused xmlns:*.
const removeEditorDataKeepPartnerLabels = {
  name: 'removeEditorDataKeepPartnerLabels',
  fn: () => ({
    element: {
      enter: (node, parentNode) => {
        if (isEditorName(node.name)) {
          if (node.attributes.id == null) {
            parentNode.children = parentNode.children.filter((child) => child !== node);
            return;
          }
          node.attributes = { id: node.attributes.id };
          node.children = [];
          return;
        }
        for (const [name, value] of Object.entries(node.attributes)) {
          if (name === 'inkscape:label' && PARTNER_LABEL.test(value)) continue;
          if (isEditorName(name)) delete node.attributes[name];
        }
      },
    },
  }),
};

const DISPLAY_NONE = /(^|;)\s*display\s*:\s*none\s*(;|$)/;

// Only display:none, exactly. SVGO's removeHiddenElems also drops
// unreferenced clipPaths/filters and empty defs, so it stays off.
const removeDisplayNone = {
  name: 'removeDisplayNone',
  fn: () => ({
    element: {
      enter: (node, parentNode) => {
        if (node.attributes.display === 'none' || DISPLAY_NONE.test(node.attributes.style ?? '')) {
          parentNode.children = parentNode.children.filter((child) => child !== node);
          node.children = [];
        }
      },
    },
  }),
};

export default {
  multipass: true,
  js2svg: { pretty: false },
  plugins: [
    removeDisplayNone,
    removeEditorDataKeepPartnerLabels,
    {
      name: 'preset-default',
      params: {
        overrides: {
          // Replaced by removeEditorDataKeepPartnerLabels above.
          removeEditorsNSData: false,
          // Keep every rendered id, element and element type.
          cleanupIds: false,
          removeHiddenElems: false,
          removeEmptyContainers: false,
          removeEmptyText: false,
          removeUselessDefs: false,
          collapseGroups: false,
          convertShapeToPath: false,
          convertEllipseToCircle: false,
          mergePaths: false,
          removeDesc: false,
          removeUnknownsAndDefaults: { keepRoleAttr: true, keepAriaAttrs: true, keepDataAttrs: true },
          // Stroke widths, x/y/width/height: keep their precision.
          cleanupNumericValues: { floatPrecision: 3 },
          // Lossless rewrites only: no arcs or lines fitted to curves.
          convertPathData: {
            floatPrecision: GEOMETRY_PRECISION,
            makeArcs: false,
            straightCurves: false,
            convertToQ: false,
            smartArcRounding: false,
          },
        },
      },
    },
    { name: 'cleanupListOfValues', params: { floatPrecision: GEOMETRY_PRECISION } },
  ],
};
