import { jest } from '@jest/globals';
// tests/js/templates_utils.test.js

document.body.innerHTML = `
  <div id="template-list"></div>
`;

let isMobile;
let updateGridLayout;
let templateBelongsToGroup;
let templateMatchesSearch;

beforeAll(async () => {
  const mod = await import('../../app/static/js/templates.js');
  isMobile = mod.isMobile;
  updateGridLayout = mod.updateGridLayout;
  templateBelongsToGroup = mod.templateBelongsToGroup;
  templateMatchesSearch = mod.templateMatchesSearch;
});

describe('templates.js utilities', () => {
  test('isMobile detects hover capability', () => {
    window.matchMedia = jest.fn().mockImplementation(query => ({
      matches: query === '(hover: none)',
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));

    expect(isMobile()).toBe(true);

    window.matchMedia = jest.fn().mockImplementation(() => ({
      matches: false,
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));

    expect(isMobile()).toBe(false);
  });

  test('updateGridLayout sets grid columns', () => {
    const list = document.getElementById('template-list');
    window.matchMedia = jest.fn().mockImplementation(query => ({
      matches: query === '(hover: none)',
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));
    updateGridLayout();
    expect(list.style.gridTemplateColumns).toBe('1fr');

    window.matchMedia = jest.fn().mockImplementation(() => ({
      matches: false,
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));
    updateGridLayout();
    expect(list.style.gridTemplateColumns).toBe('repeat(auto-fit, minmax(50px, var(--grid-item-width, 360px)))');
  });

  test('templateBelongsToGroup correctly matches groups', () => {
    const template = { groups: 'a,b' };
    expect(templateBelongsToGroup(template, 'a')).toBe(true);
    expect(templateBelongsToGroup(template, 'c')).toBe(false);
    expect(templateBelongsToGroup(template, 'all')).toBe(true);
  });

  test('templateMatchesSearch checks name and groups', () => {
    const template = { name: 'Cam1', groups: 'inside,outside' };
    expect(templateMatchesSearch(template, 'cam')).toBe(true);
    expect(templateMatchesSearch(template, 'side')).toBe(true);
    expect(templateMatchesSearch(template, 'none')).toBe(false);
  });
});
