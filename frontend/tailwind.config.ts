import type { Config } from 'tailwindcss';
const config: Config = { content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'], theme: { extend: { colors: { ink:'#0b1220', panel:'#111b2d', line:'#263349', accent:'#63e6be' }, boxShadow:{soft:'0 18px 60px rgba(0,0,0,.18)'} } }, plugins: [] };
export default config;
