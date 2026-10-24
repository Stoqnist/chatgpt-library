'use strict';
(() => {
  const {locale, messages, sourceTextKeys} = window.STOQ_LOCALE;
  const t = (key, values = {}) => {
    if (!Object.hasOwn(messages, key)) throw new Error('Missing translation: ' + key);
    return messages[key].replace(/\{(\w+)\}/g, (_, name) => {
      if (!Object.hasOwn(values, name)) throw new Error('Missing translation value: ' + name);
      return String(values[name]);
    });
  };
  const source = value => {
    const key = sourceTextKeys[value];
    if (!key) throw new Error('Uncatalogued source text: ' + value);
    return t(key);
  };
  const money = amount => new Intl.NumberFormat(locale, {style:'currency', currency:'EUR'}).format(Number(amount));
  window.StoqI18n = Object.freeze({locale, t, source, money});
  // Share the selected language in the URL, without cookies or browser storage.
  const updateLanguageLinks = () => document.querySelectorAll('[data-language-link]').forEach(link => {
    const url = new URL(link.href);
    url.hash = location.hash;
    link.href = url.pathname + url.hash;
  });
  window.addEventListener('hashchange', updateLanguageLinks);
  updateLanguageLinks();
  const video = document.getElementById('story-video');
  video?.addEventListener('error', () => {
    document.getElementById('video-status').textContent = t('video.unavailable');
    document.getElementById('film-transcript').open = true;
  });
})();
