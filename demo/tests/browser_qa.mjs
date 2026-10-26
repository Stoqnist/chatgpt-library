// Browser smoke test against the same Docker release artifact used by HTTP checks.
// Uses installed Chrome on the GitHub runner; screenshots are QA evidence, not deployment.
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = process.env.STOQ_TEST_URL || 'http://127.0.0.1:8092';
const widthCases = [320, 390, 1280];
const locales = ['en', 'nl', 'bg'];
const paths = ['', 'demos/', 'demos/gunter/', 'demos/purchase/'];
const screenshotDir = 'demo/screenshots';
await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
let checked = 0;
try {
  for (const locale of locales) {
    const prefix = locale === 'en' ? '/' : `/${locale}/`;
    for (const width of widthCases) {
      const context = await browser.newContext({
        viewport: { width, height: 900 },
        isMobile: width < 500,
        hasTouch: width < 500,
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(error.message));
      for (const route of paths) {
        const url = `${base}${prefix}${route}`;
        const response = await page.goto(url, { waitUntil: 'load', timeout: 30000 });
        assert.equal(response.status(), 200, `${url} status`);
        assert.equal(await page.locator('html').getAttribute('lang'), locale, url);
        assert.equal(await page.locator('meta[property="og:url"]').getAttribute('content'), `https://stoq.page${prefix}${route}`);
        assert.equal(await page.locator('link[rel="icon"]').getAttribute('href'), '/assets/stoqnist-mark.svg');
        const sizes = await page.evaluate(() => ({
          viewport: window.innerWidth,
          document: document.documentElement.scrollWidth,
          body: document.body.scrollWidth,
        }));
        assert(
          sizes.document <= sizes.viewport + 2 && sizes.body <= sizes.viewport + 2,
          `Horizontal overflow: ${locale} ${width}px ${route || 'home'} ${JSON.stringify(sizes)}`,
        );
        assert.equal(await page.locator('h1').count(), 1, `${url} should have one main heading`);
        if (route === '' && width < 500) {
          const topBar = page.locator('.page-home .site-top');
          assert.equal(await topBar.locator('.site-mark').isVisible(), false,
            'The mobile homepage should not repeat the hero wordmark');
          assert(await topBar.locator('.site-nav-link').isVisible(),
            'Demos navigation must remain available');
          const spacing = await page.evaluate(() => {
            const banner = document.querySelector('.home-banner').getBoundingClientRect();
            const idea = document.querySelector('.page-home .idea').getBoundingClientRect();
            return { gap: idea.top - banner.bottom, viewport: innerWidth };
          });
          assert(spacing.gap >= 0 && spacing.gap <= 48,
            'Excess hero-to-idea gap: '+locale+' '+width+' '+JSON.stringify(spacing));
        }
        if (route === '') {
          const banner = await page.locator('.home-banner .guided-hero-art').evaluate(el => {
            const styles = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return {
              width: rect.width,
              height: rect.height,
              background: styles.backgroundImage,
              fit: styles.backgroundSize,
            };
          });
          assert(banner.background.includes('stoqnist-family-hero.webp'),
            `Shared family panorama not applied: ${locale} ${width}px ${banner.background}`);
          if (width < 960) {
            assert(banner.background.includes('3d116045c58659315a345f1d91130f06faa5862c'),
              `Unversioned family photo on ${locale} mobile ${width}px`);
            assert.equal(banner.fit, 'contain', `Family art is cropped on ${locale} ${width}px`);
            assert(Math.abs(banner.width / banner.height - 3) < 0.025,
              `Full family panorama ratio lost on ${locale} ${width}px: ${banner.width} × ${banner.height}`);
          }
        }
        if (route === 'demos/gunter/') {
          const player = page.locator('.film-player');
          const video = page.locator('#story-video');
          const rect = await player.boundingBox();
          assert(rect && rect.x >= -2 && rect.x + rect.width <= width + 2,
            `Film player offscreen ${locale} ${width}px: ${JSON.stringify(rect)}`);
          assert.equal(await video.locator('source').getAttribute('src'), '/media/gunter-morning-en.mp4');
          if (locale !== 'en') {
            const track = video.locator('track');
            assert.equal(await track.getAttribute('srclang'), locale);
            assert.equal(await track.getAttribute('src'), `/media/gunter-morning-${locale}.vtt`);
            assert.notEqual(await track.getAttribute('default'), null, `Captions are default on ${locale}`);
          }
          if (width === 390) {
            await page.locator('#film-play').click({ timeout: 10000 });
            await page.waitForFunction(
              () => document.getElementById('story-video')?.currentTime > 0.1,
              null, { timeout: 20000 },
            );
            if (locale !== 'en') {
              await page.waitForFunction(
                () => document.querySelector('#story-video track')?.track?.cues?.length === 9,
                null, { timeout: 15000 },
              );
              const cues = await page.evaluate(() => {
                const track = document.querySelector('#story-video track').track;
                return {
                  count: track.cues.length,
                  mode: track.mode,
                  firstLine: track.cues[0].line,
                  lastEnd: track.cues[8].endTime,
                };
              });
              assert.equal(cues.mode, 'showing', `${locale} subtitles are active`);
              assert.equal(cues.firstLine, 8, `${locale} subtitles should avoid bottom burned-in copy`);
              assert(cues.lastEnd < 55, `${locale} captions exceed video duration`);
            }
          }
        }
        if ((width === 390 || width === 1280) && (route === '' || route === 'demos/gunter/')) {
          const name = route ? 'gunter' : 'home';
          await page.screenshot({
            path: `${screenshotDir}/${locale}-${name}-${width}.png`,
            fullPage: true,
            animations: 'disabled',
          });
        }
        checked++;
      }
      assert.deepEqual(pageErrors, [], `${locale} ${width}px JavaScript runtime errors`);
      await context.close();
    }
  }
  console.log(`PASS: ${checked} browser pages, nine video layouts, three real playback tests, two translated WebVTT tracks`);
} finally {
  await browser.close();
}
