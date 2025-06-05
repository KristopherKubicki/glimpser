import { jest } from '@jest/globals';

document.body.innerHTML = `
  <nav>
    <button id="menu-toggle"></button>
    <div class="nav-left"><a id="link" href="#"></a></div>
  </nav>
`;

let initNav;

beforeAll(async () => {
  const mod = await import('../../app/static/js/nav.js');
  initNav = mod.initNav;
});

describe('mobile nav', () => {
  beforeEach(() => {
    document.querySelector('nav').classList.remove('active');
  });

  test('link click closes menu', () => {
    initNav();
    document.dispatchEvent(new Event('DOMContentLoaded'));
    const menuToggle = document.getElementById('menu-toggle');
    menuToggle.click();
    expect(document.querySelector('nav').classList.contains('active')).toBe(true);
    document.getElementById('link').click();
    expect(document.querySelector('nav').classList.contains('active')).toBe(false);
  });
});
