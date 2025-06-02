// tests/js/slider_height.test.js

document.body.innerHTML = `
  <div id="template-list"></div>
  <input id="grid-width-slider" type="range" value="360">
`;

const { initTemplates } = require('../../app/static/js/templates.js');

describe('grid width slider', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    document.getElementById('template-list').style = '';
  });

  test('adjusts height variable on input', () => {
    initTemplates();
    document.dispatchEvent(new Event('DOMContentLoaded'));
    const slider = document.getElementById('grid-width-slider');
    slider.value = '320';
    slider.dispatchEvent(new Event('input'));
    const list = document.getElementById('template-list');
    expect(list.style.getPropertyValue('--grid-item-width')).toBe('320px');
    expect(list.style.getPropertyValue('--grid-item-height')).toBe('180px');
  });
});
