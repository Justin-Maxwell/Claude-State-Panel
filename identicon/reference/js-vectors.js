// Generate identicon conformance vectors from stewartlord/identicon.js.
//
// This file is ours; the library under vendor/ is not. It is committed rather
// than fetched so that vectors.json can be re-derived by anyone, offline, for
// as long as this repository exists -- a reference that has to be downloaded
// is a reference that can disappear, and one did during the week this was
// written.
//
// SVG rather than PNG, because the grid is then recoverable exactly: the
// library emits one <rect> per *foreground* cell inside a <g> carrying the
// fill, and puts the background on the root element's style. The rects alone
// are the pattern, with no pixel decoding and no resampling to argue about.
//
//   node js-vectors.js <key> [key...]

const crypto = require('crypto');
const Identicon = require('./vendor/identicon.js');

const CELL = 10;

function rgb(rgba) {
  const [r, g, b] = rgba.split(',').map(n => parseInt(n, 10));
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}

function vector(key) {
  const md5 = crypto.createHash('md5').update(key).digest('hex');
  const svg = new Identicon(md5, { size: 50, margin: 0, format: 'svg' }).toString(true);

  const grid = Array.from({ length: 5 }, () => Array(5).fill(0));
  for (const [, x, y] of svg.matchAll(/<rect\s+x='(\d+)'\s+y='(\d+)'/g)) {
    grid[y / CELL][x / CELL] = 1;
  }

  return {
    key,
    md5,
    grid: grid.map(r => r.join('')),
    foreground: rgb(svg.match(/fill:rgba\(([^)]+)\)/)[1]),
    background: rgb(svg.match(/background-color:rgba\(([^)]+)\)/)[1]),
  };
}

console.log(JSON.stringify(process.argv.slice(2).map(vector), null, 1));
