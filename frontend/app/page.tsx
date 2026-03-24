'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ChatWidget from '@/components/ChatWidget'
import { api, type Category } from '@/lib/api'
import { useLang } from '@/lib/useLang'
import { categoryName, t } from '@/lib/translations'

// ── Category visuals: gradient + SVG illustration ─────────────────────────────
const CAT_VISUALS: Record<string, { grad: string; svg: string }> = {
  'shlanhy-dlya-promyslovosti': {
    grad: 'linear-gradient(135deg, #1a0a0a 0%, #3d1010 50%, #c41e1e22 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="hg1" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#c41e1e" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="#c41e1e" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <!-- Hose cross-sections -->
      <circle cx="65" cy="65" r="52" fill="none" stroke="#c41e1e" stroke-width="12" opacity="0.25"/>
      <circle cx="65" cy="65" r="52" fill="none" stroke="#ff4444" stroke-width="2" opacity="0.6"/>
      <circle cx="65" cy="65" r="38" fill="none" stroke="#888" stroke-width="1" opacity="0.4" stroke-dasharray="4 3"/>
      <circle cx="65" cy="65" r="22" fill="#c41e1e" opacity="0.15"/>
      <circle cx="65" cy="65" r="22" fill="none" stroke="#ff6666" stroke-width="2" opacity="0.7"/>
      <circle cx="65" cy="65" r="10" fill="#c41e1e" opacity="0.4"/>
      <!-- Second hose section -->
      <circle cx="148" cy="55" r="34" fill="none" stroke="#c41e1e" stroke-width="8" opacity="0.18"/>
      <circle cx="148" cy="55" r="34" fill="none" stroke="#ff4444" stroke-width="1.5" opacity="0.5"/>
      <circle cx="148" cy="55" r="20" fill="none" stroke="#888" stroke-width="1" opacity="0.3" stroke-dasharray="3 2"/>
      <circle cx="148" cy="55" r="8" fill="#c41e1e" opacity="0.3"/>
      <!-- Connecting tube -->
      <path d="M65 13 Q100 5 148 21" fill="none" stroke="#ff4444" stroke-width="3" opacity="0.4"/>
      <path d="M65 117 Q100 125 148 89" fill="none" stroke="#ff4444" stroke-width="3" opacity="0.4"/>
      <!-- Braid texture lines -->
      <path d="M30 65 Q50 50 80 65 Q110 80 130 65" fill="none" stroke="#c41e1e" stroke-width="1" opacity="0.2"/>
      <path d="M30 65 Q50 80 80 65 Q110 50 130 65" fill="none" stroke="#c41e1e" stroke-width="1" opacity="0.2"/>
      <circle cx="65" cy="65" r="52" fill="url(#hg1)"/>
    </svg>`,
  },
  'sylova-hidravlika': {
    grad: 'linear-gradient(135deg, #050e1f 0%, #0a2040 50%, #1a4a8022 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="cyl" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#1e40af" stop-opacity="0.6"/>
          <stop offset="50%" stop-color="#3b82f6" stop-opacity="0.8"/>
          <stop offset="100%" stop-color="#1e40af" stop-opacity="0.4"/>
        </linearGradient>
      </defs>
      <!-- Hydraulic cylinder body -->
      <rect x="20" y="45" width="130" height="40" rx="4" fill="url(#cyl)"/>
      <rect x="20" y="45" width="130" height="40" rx="4" fill="none" stroke="#60a5fa" stroke-width="1.5" opacity="0.8"/>
      <!-- Piston rod -->
      <rect x="150" y="56" width="40" height="18" rx="2" fill="#93c5fd" opacity="0.7"/>
      <rect x="150" y="56" width="40" height="18" rx="2" fill="none" stroke="#3b82f6" stroke-width="1"/>
      <!-- Piston inside -->
      <rect x="115" y="47" width="8" height="36" fill="#1e3a6e" opacity="0.8"/>
      <rect x="115" y="47" width="8" height="36" fill="none" stroke="#60a5fa" stroke-width="1"/>
      <!-- End cap left -->
      <rect x="14" y="40" width="10" height="50" rx="3" fill="#1e40af" opacity="0.9"/>
      <rect x="14" y="40" width="10" height="50" rx="3" fill="none" stroke="#60a5fa" stroke-width="1.5"/>
      <!-- Ports -->
      <circle cx="50" cy="45" r="5" fill="none" stroke="#60a5fa" stroke-width="1.5" opacity="0.7"/>
      <line x1="50" y1="40" x2="50" y2="33" stroke="#60a5fa" stroke-width="2" opacity="0.6"/>
      <circle cx="90" cy="85" r="5" fill="none" stroke="#60a5fa" stroke-width="1.5" opacity="0.7"/>
      <line x1="90" y1="90" x2="90" y2="97" stroke="#60a5fa" stroke-width="2" opacity="0.6"/>
      <!-- Pressure lines -->
      <path d="M25 65 Q40 55 55 65 Q70 75 85 65 Q100 55 115 65" fill="none" stroke="#93c5fd" stroke-width="1" opacity="0.3"/>
      <!-- Highlight line -->
      <line x1="22" y1="50" x2="148" y2="50" stroke="white" stroke-width="0.5" opacity="0.2"/>
      <!-- Small gauge -->
      <circle cx="168" cy="100" r="18" fill="#0a1628" stroke="#3b82f6" stroke-width="1.5" opacity="0.9"/>
      <path d="M157 100 A11 11 0 0 1 179 100" fill="none" stroke="#60a5fa" stroke-width="1" opacity="0.5"/>
      <line x1="168" y1="100" x2="175" y2="93" stroke="#93c5fd" stroke-width="1.5" opacity="0.8"/>
      <circle cx="168" cy="100" r="2" fill="#60a5fa"/>
    </svg>`,
  },
  'promyslova-armatura': {
    grad: 'linear-gradient(135deg, #0d0520 0%, #1e0a3d 50%, #4c1d9522 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="vg" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#7c3aed" stop-opacity="0.4"/>
          <stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <!-- Ball valve body -->
      <rect x="30" y="52" width="55" height="26" rx="3" fill="#4c1d95" opacity="0.7"/>
      <rect x="30" y="52" width="55" height="26" rx="3" fill="none" stroke="#a78bfa" stroke-width="1.5"/>
      <!-- Ball -->
      <circle cx="90" cy="65" r="22" fill="#1e0a3d" stroke="#7c3aed" stroke-width="2" opacity="0.9"/>
      <circle cx="90" cy="65" r="22" fill="url(#vg)"/>
      <circle cx="90" cy="65" r="12" fill="none" stroke="#a78bfa" stroke-width="1.5" opacity="0.6"/>
      <!-- Flow port through ball -->
      <ellipse cx="90" cy="65" rx="7" ry="12" fill="#7c3aed" opacity="0.5" stroke="#c4b5fd" stroke-width="1"/>
      <!-- Right body -->
      <rect x="112" y="52" width="55" height="26" rx="3" fill="#4c1d95" opacity="0.7"/>
      <rect x="112" y="52" width="55" height="26" rx="3" fill="none" stroke="#a78bfa" stroke-width="1.5"/>
      <!-- Stem (top) -->
      <rect x="84" y="28" width="12" height="22" rx="2" fill="#6d28d9" stroke="#a78bfa" stroke-width="1"/>
      <!-- Handle -->
      <rect x="68" y="22" width="44" height="8" rx="4" fill="#7c3aed" stroke="#c4b5fd" stroke-width="1.5"/>
      <!-- Flow direction arrows -->
      <path d="M10 65 L28 65 M172 65 L190 65" stroke="#a78bfa" stroke-width="2" stroke-dasharray="3 2" opacity="0.5"/>
      <polygon points="25,62 30,65 25,68" fill="#a78bfa" opacity="0.6"/>
      <polygon points="188,62 193,65 188,68" fill="#a78bfa" opacity="0.6"/>
      <!-- Hex bolts on flanges -->
      <circle cx="40" cy="58" r="3" fill="none" stroke="#c4b5fd" stroke-width="1" opacity="0.5"/>
      <circle cx="40" cy="72" r="3" fill="none" stroke="#c4b5fd" stroke-width="1" opacity="0.5"/>
      <circle cx="157" cy="58" r="3" fill="none" stroke="#c4b5fd" stroke-width="1" opacity="0.5"/>
      <circle cx="157" cy="72" r="3" fill="none" stroke="#c4b5fd" stroke-width="1" opacity="0.5"/>
    </svg>`,
  },
  'promyslova-pnevmatyka': {
    grad: 'linear-gradient(135deg, #041a15 0%, #083d2e 50%, #0d9a6a22 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <!-- Air flow background -->
      <path d="M10 50 Q50 35 90 50 Q130 65 170 50 Q185 45 195 48" fill="none" stroke="#10b981" stroke-width="1.5" opacity="0.25" stroke-dasharray="5 3"/>
      <path d="M10 65 Q50 50 90 65 Q130 80 170 65 Q185 60 195 63" fill="none" stroke="#34d399" stroke-width="1.5" opacity="0.3" stroke-dasharray="5 3"/>
      <path d="M10 80 Q50 65 90 80 Q130 95 170 80 Q185 75 195 78" fill="none" stroke="#10b981" stroke-width="1.5" opacity="0.25" stroke-dasharray="5 3"/>
      <!-- Pneumatic cylinder -->
      <rect x="30" y="48" width="90" height="34" rx="3" fill="#064e3b" opacity="0.8"/>
      <rect x="30" y="48" width="90" height="34" rx="3" fill="none" stroke="#34d399" stroke-width="1.5"/>
      <!-- Rod -->
      <rect x="120" y="58" width="50" height="14" rx="2" fill="#6ee7b7" opacity="0.5"/>
      <rect x="120" y="58" width="50" height="14" rx="2" fill="none" stroke="#10b981" stroke-width="1"/>
      <!-- Piston -->
      <rect x="95" y="50" width="6" height="30" fill="#065f46" stroke="#34d399" stroke-width="1"/>
      <!-- End cap -->
      <rect x="22" y="43" width="10" height="44" rx="3" fill="#065f46" stroke="#34d399" stroke-width="1.5"/>
      <!-- Air ports with hose connectors -->
      <rect x="50" y="38" width="8" height="10" rx="1" fill="#065f46" stroke="#34d399" stroke-width="1"/>
      <rect x="80" y="82" width="8" height="10" rx="1" fill="#065f46" stroke="#34d399" stroke-width="1"/>
      <!-- Pressure bubbles -->
      <circle cx="45" cy="65" r="4" fill="#10b981" opacity="0.2" stroke="#34d399" stroke-width="0.5"/>
      <circle cx="60" cy="58" r="3" fill="#10b981" opacity="0.15" stroke="#34d399" stroke-width="0.5"/>
      <circle cx="75" cy="70" r="5" fill="#10b981" opacity="0.2" stroke="#34d399" stroke-width="0.5"/>
      <!-- Speed controllers -->
      <circle cx="165" cy="40" r="12" fill="#041a15" stroke="#34d399" stroke-width="1.5" opacity="0.9"/>
      <line x1="159" y1="40" x2="171" y2="40" stroke="#34d399" stroke-width="1.5" opacity="0.7"/>
      <line x1="165" y1="34" x2="165" y2="46" stroke="#34d399" stroke-width="1.5" opacity="0.7"/>
      <line x1="160" y1="36" x2="170" y2="44" stroke="#6ee7b7" stroke-width="1" opacity="0.5"/>
    </svg>`,
  },
  'pretsyziyna-armatura': {
    grad: 'linear-gradient(135deg, #0a0a1a 0%, #1a1a3d 50%, #2563eb22 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <!-- Precision fitting - tube fitting cross section -->
      <!-- Main tube -->
      <rect x="10" y="58" width="80" height="14" rx="2" fill="#1e3a8a" opacity="0.8" stroke="#60a5fa" stroke-width="1"/>
      <rect x="10" y="61" width="80" height="4" rx="1" fill="white" opacity="0.06"/>
      <!-- Compression nut -->
      <rect x="88" y="50" width="20" height="30" rx="2" fill="#1e40af" stroke="#93c5fd" stroke-width="1.5" opacity="0.9"/>
      <!-- Ferrule (cone) -->
      <polygon points="108,58 122,53 122,77 108,72" fill="#3b82f6" opacity="0.8" stroke="#93c5fd" stroke-width="1"/>
      <!-- Body -->
      <rect x="120" y="48" width="30" height="34" rx="3" fill="#1e3a8a" stroke="#60a5fa" stroke-width="1.5" opacity="0.9"/>
      <!-- Outlet tube -->
      <rect x="150" y="58" width="40" height="14" rx="2" fill="#1e3a8a" opacity="0.8" stroke="#60a5fa" stroke-width="1"/>
      <!-- O-ring indicator lines -->
      <line x1="91" y1="54" x2="91" y2="76" stroke="#93c5fd" stroke-width="1" opacity="0.5"/>
      <line x1="96" y1="54" x2="96" y2="76" stroke="#93c5fd" stroke-width="1" opacity="0.5"/>
      <!-- Hex flats on nut -->
      <line x1="88" y1="53" x2="88" y2="57" stroke="#bfdbfe" stroke-width="1.5" opacity="0.4"/>
      <line x1="108" y1="53" x2="108" y2="57" stroke="#bfdbfe" stroke-width="1.5" opacity="0.4"/>
      <line x1="88" y1="73" x2="108" y2="73" stroke="#bfdbfe" stroke-width="0.5" opacity="0.2"/>
      <!-- Second fitting at angle -->
      <rect x="140" y="20" width="14" height="32" rx="2" fill="#1e3a8a" opacity="0.6" stroke="#60a5fa" stroke-width="1"/>
      <!-- Dimension arrows -->
      <line x1="10" y1="100" x2="90" y2="100" stroke="#3b82f6" stroke-width="0.5" opacity="0.4"/>
      <line x1="10" y1="96" x2="10" y2="104" stroke="#3b82f6" stroke-width="0.5" opacity="0.4"/>
      <line x1="90" y1="96" x2="90" y2="104" stroke="#3b82f6" stroke-width="0.5" opacity="0.4"/>
      <!-- Crosshair center marker -->
      <circle cx="135" cy="65" r="3" fill="none" stroke="#93c5fd" stroke-width="1" opacity="0.5"/>
      <line x1="131" y1="65" x2="139" y2="65" stroke="#93c5fd" stroke-width="0.5" opacity="0.4"/>
      <line x1="135" y1="61" x2="135" y2="69" stroke="#93c5fd" stroke-width="0.5" opacity="0.4"/>
    </svg>`,
  },
  'vymiryuvalni-systemy-ta-manometry': {
    grad: 'linear-gradient(135deg, #1a0f00 0%, #3d2600 50%, #f59e0b22 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="gg" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#d97706" stop-opacity="0.15"/>
          <stop offset="100%" stop-color="#d97706" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <!-- Pressure gauge -->
      <circle cx="75" cy="65" r="52" fill="#1a0f00" stroke="#d97706" stroke-width="2" opacity="0.9"/>
      <circle cx="75" cy="65" r="52" fill="url(#gg)"/>
      <circle cx="75" cy="65" r="44" fill="#0f0800" stroke="#78350f" stroke-width="1" opacity="0.8"/>
      <!-- Scale arc -->
      <path d="M35 90 A45 45 0 1 1 115 90" fill="none" stroke="#92400e" stroke-width="2" opacity="0.5"/>
      <!-- Tick marks -->
      <line x1="75" y1="22" x2="75" y2="30" stroke="#fbbf24" stroke-width="2" opacity="0.8"/>
      <line x1="75" y1="100" x2="75" y2="108" stroke="#fbbf24" stroke-width="2" opacity="0.8"/>
      <line x1="30" y1="65" x2="38" y2="65" stroke="#fbbf24" stroke-width="2" opacity="0.8"/>
      <line x1="112" y1="65" x2="120" y2="65" stroke="#fbbf24" stroke-width="2" opacity="0.8"/>
      <line x1="42" y1="35" x2="48" y2="40" stroke="#fbbf24" stroke-width="1.5" opacity="0.6"/>
      <line x1="100" y1="35" x2="106" y2="41" stroke="#fbbf24" stroke-width="1.5" opacity="0.6"/>
      <line x1="38" y1="92" x2="45" y2="88" stroke="#fbbf24" stroke-width="1.5" opacity="0.6"/>
      <line x1="104" y1="93" x2="111" y2="89" stroke="#fbbf24" stroke-width="1.5" opacity="0.6"/>
      <!-- Minor ticks -->
      <line x1="75" y1="25" x2="75" y2="29" stroke="#92400e" stroke-width="1" opacity="0.5"/>
      <line x1="55" y1="29" x2="58" y2="33" stroke="#92400e" stroke-width="1" opacity="0.5"/>
      <line x1="95" y1="29" x2="92" y2="33" stroke="#92400e" stroke-width="1" opacity="0.5"/>
      <!-- Needle pointing to ~75% -->
      <line x1="75" y1="65" x2="105" y2="38" stroke="#ef4444" stroke-width="2" opacity="0.95"/>
      <circle cx="75" cy="65" r="4" fill="#d97706" stroke="#fbbf24" stroke-width="1"/>
      <!-- Center dot -->
      <circle cx="75" cy="65" r="2" fill="#fbbf24"/>
      <!-- Bottom connection -->
      <rect x="68" y="115" width="14" height="12" rx="2" fill="#78350f" stroke="#d97706" stroke-width="1"/>
      <!-- Second small gauge -->
      <circle cx="155" cy="50" r="28" fill="#1a0f00" stroke="#d97706" stroke-width="1.5" opacity="0.8"/>
      <circle cx="155" cy="50" r="22" fill="#0f0800" stroke="#92400e" stroke-width="0.5" opacity="0.6"/>
      <path d="M133 65 A24 24 0 1 1 177 65" fill="none" stroke="#92400e" stroke-width="1.5" opacity="0.4"/>
      <line x1="155" y1="50" x2="165" y2="35" stroke="#fbbf24" stroke-width="1.5" opacity="0.8"/>
      <circle cx="155" cy="50" r="2.5" fill="#d97706"/>
    </svg>`,
  },
  'ochystka-ta-zmyvannya': {
    grad: 'linear-gradient(135deg, #001a1a 0%, #003d3d 50%, #0891b222 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <!-- High pressure lance/nozzle -->
      <!-- Handle grip -->
      <rect x="10" y="55" width="70" height="20" rx="8" fill="#164e63" stroke="#22d3ee" stroke-width="1.5" opacity="0.8"/>
      <!-- Grip texture -->
      <line x1="20" y1="55" x2="20" y2="75" stroke="#0891b2" stroke-width="1" opacity="0.3"/>
      <line x1="28" y1="55" x2="28" y2="75" stroke="#0891b2" stroke-width="1" opacity="0.3"/>
      <line x1="36" y1="55" x2="36" y2="75" stroke="#0891b2" stroke-width="1" opacity="0.3"/>
      <!-- Lance tube -->
      <rect x="78" y="60" width="80" height="10" rx="2" fill="#0e7490" stroke="#22d3ee" stroke-width="1"/>
      <rect x="78" y="62" width="80" height="3" fill="white" opacity="0.06"/>
      <!-- Nozzle tip -->
      <polygon points="158,56 175,65 158,74" fill="#0891b2" stroke="#67e8f9" stroke-width="1.5" opacity="0.9"/>
      <!-- Trigger -->
      <path d="M50 75 L45 95 L55 95 L60 75" fill="#0e7490" stroke="#22d3ee" stroke-width="1" opacity="0.7"/>
      <!-- Water spray fan -->
      <line x1="176" y1="65" x2="198" y2="45" stroke="#67e8f9" stroke-width="1.5" opacity="0.7" stroke-linecap="round"/>
      <line x1="176" y1="65" x2="200" y2="55" stroke="#22d3ee" stroke-width="1.5" opacity="0.8" stroke-linecap="round"/>
      <line x1="176" y1="65" x2="200" y2="65" stroke="#67e8f9" stroke-width="2" opacity="0.9" stroke-linecap="round"/>
      <line x1="176" y1="65" x2="200" y2="75" stroke="#22d3ee" stroke-width="1.5" opacity="0.8" stroke-linecap="round"/>
      <line x1="176" y1="65" x2="198" y2="85" stroke="#67e8f9" stroke-width="1.5" opacity="0.7" stroke-linecap="round"/>
      <!-- Water droplets -->
      <circle cx="192" cy="42" r="2" fill="#67e8f9" opacity="0.6"/>
      <circle cx="196" cy="52" r="1.5" fill="#22d3ee" opacity="0.7"/>
      <circle cx="197" cy="65" r="2" fill="#67e8f9" opacity="0.8"/>
      <circle cx="196" cy="78" r="1.5" fill="#22d3ee" opacity="0.7"/>
      <circle cx="192" cy="88" r="2" fill="#67e8f9" opacity="0.6"/>
      <!-- Pressure connection -->
      <rect x="4" y="60" width="8" height="10" rx="1" fill="#0e7490" stroke="#22d3ee" stroke-width="1" opacity="0.8"/>
      <!-- Water surface ripples below -->
      <path d="M40 108 Q60 103 80 108 Q100 113 120 108 Q140 103 160 108" fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.25"/>
      <path d="M50 116 Q70 111 90 116 Q110 121 130 116 Q150 111 170 116" fill="none" stroke="#67e8f9" stroke-width="1" opacity="0.2"/>
    </svg>`,
  },
  'prystroyi-ta-aksesuary': {
    grad: 'linear-gradient(135deg, #0f0f0f 0%, #1e1e2e 50%, #64748b22 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <!-- Wrench -->
      <g transform="rotate(-30, 80, 65)">
        <rect x="50" y="60" width="70" height="10" rx="2" fill="#334155" stroke="#94a3b8" stroke-width="1.5"/>
        <circle cx="45" cy="65" r="16" fill="#1e293b" stroke="#94a3b8" stroke-width="1.5"/>
        <circle cx="45" cy="65" r="16" fill="none" stroke="#64748b" stroke-width="1" opacity="0.3"/>
        <!-- Wrench opening -->
        <path d="M35 57 L35 73" stroke="#1e293b" stroke-width="10" stroke-linecap="round"/>
        <path d="M35 57 L45 57" stroke="#94a3b8" stroke-width="1.5"/>
        <path d="M35 73 L45 73" stroke="#94a3b8" stroke-width="1.5"/>
        <!-- End of wrench -->
        <circle cx="124" cy="65" r="12" fill="#1e293b" stroke="#94a3b8" stroke-width="1.5"/>
        <path d="M114 59 L114 71" stroke="#1e293b" stroke-width="8" stroke-linecap="round"/>
        <path d="M114 59 L122 59" stroke="#94a3b8" stroke-width="1.5"/>
        <path d="M114 71 L122 71" stroke="#94a3b8" stroke-width="1.5"/>
      </g>
      <!-- Hose clamp -->
      <circle cx="148" cy="65" r="28" fill="none" stroke="#94a3b8" stroke-width="3" opacity="0.7"/>
      <circle cx="148" cy="65" r="28" fill="none" stroke="#64748b" stroke-width="6" opacity="0.2"/>
      <!-- Clamp screw head -->
      <rect x="170" y="54" width="14" height="10" rx="2" fill="#334155" stroke="#94a3b8" stroke-width="1.5"/>
      <line x1="174" y1="54" x2="174" y2="64" stroke="#64748b" stroke-width="1" opacity="0.5"/>
      <line x1="177" y1="54" x2="177" y2="64" stroke="#64748b" stroke-width="1" opacity="0.5"/>
      <line x1="180" y1="54" x2="180" y2="64" stroke="#64748b" stroke-width="1" opacity="0.5"/>
      <!-- Screwdriver -->
      <rect x="8" y="40" width="5" height="50" rx="2" fill="#475569" stroke="#94a3b8" stroke-width="1" opacity="0.7"/>
      <polygon points="8,90 13,90 11,100 10,100" fill="#334155" stroke="#94a3b8" stroke-width="0.5" opacity="0.8"/>
      <rect x="5" y="38" width="11" height="8" rx="2" fill="#334155" stroke="#94a3b8" stroke-width="1" opacity="0.8"/>
    </svg>`,
  },
  'industrial_hoses': {
    grad: 'linear-gradient(135deg, #1a0505 0%, #2d0a0a 50%, #dc262622 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <!-- Spiral/coiled hose -->
      <path d="M20 65 Q20 25 60 25 Q100 25 100 65 Q100 105 140 105 Q180 105 180 65"
            fill="none" stroke="#dc2626" stroke-width="12" opacity="0.25" stroke-linecap="round"/>
      <path d="M20 65 Q20 25 60 25 Q100 25 100 65 Q100 105 140 105 Q180 105 180 65"
            fill="none" stroke="#ef4444" stroke-width="2" opacity="0.7" stroke-linecap="round"/>
      <!-- Outer braid suggestion -->
      <path d="M20 65 Q20 30 60 30 Q95 30 95 65 Q95 100 140 100 Q175 100 175 65"
            fill="none" stroke="#991b1b" stroke-width="1" opacity="0.4" stroke-dasharray="6 4"/>
      <!-- End fittings -->
      <rect x="8" y="57" width="14" height="16" rx="2" fill="#7f1d1d" stroke="#f87171" stroke-width="1.5"/>
      <rect x="3" y="60" width="7" height="10" rx="1" fill="#991b1b" stroke="#f87171" stroke-width="1"/>
      <rect x="178" y="57" width="14" height="16" rx="2" fill="#7f1d1d" stroke="#f87171" stroke-width="1.5"/>
      <rect x="190" y="60" width="7" height="10" rx="1" fill="#991b1b" stroke="#f87171" stroke-width="1"/>
    </svg>`,
  },
  'pneumatic': {
    grad: 'linear-gradient(135deg, #001a0a 0%, #003319 50%, #16a34a22 100%)',
    svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
      <!-- Push-in fitting / pneumatic quick connector -->
      <!-- Main body -->
      <rect x="60" y="45" width="80" height="40" rx="5" fill="#14532d" stroke="#4ade80" stroke-width="1.5" opacity="0.9"/>
      <!-- Inner tube guide -->
      <circle cx="100" cy="65" r="14" fill="#052e16" stroke="#22c55e" stroke-width="1.5"/>
      <circle cx="100" cy="65" r="8" fill="none" stroke="#4ade80" stroke-width="1" opacity="0.7"/>
      <!-- Collet teeth -->
      <circle cx="100" cy="65" r="12" fill="none" stroke="#16a34a" stroke-width="2" stroke-dasharray="4 2" opacity="0.5"/>
      <!-- Tube inserted -->
      <rect x="116" y="60" width="50" height="10" rx="2" fill="#166534" opacity="0.7" stroke="#4ade80" stroke-width="1"/>
      <!-- Left tube exit -->
      <rect x="34" y="60" width="28" height="10" rx="2" fill="#166534" opacity="0.7" stroke="#4ade80" stroke-width="1"/>
      <!-- Port labels -->
      <rect x="70" y="48" width="18" height="6" rx="1" fill="#052e16" stroke="#22c55e" stroke-width="0.5" opacity="0.7"/>
      <rect x="112" y="48" width="18" height="6" rx="1" fill="#052e16" stroke="#22c55e" stroke-width="0.5" opacity="0.7"/>
      <!-- Release collar -->
      <rect x="58" y="52" width="6" height="26" rx="2" fill="#15803d" stroke="#86efac" stroke-width="1"/>
      <rect x="136" y="52" width="6" height="26" rx="2" fill="#15803d" stroke="#86efac" stroke-width="1"/>
      <!-- Air flow arrows -->
      <path d="M20 65 L32 65" stroke="#4ade80" stroke-width="2" opacity="0.6"/>
      <polygon points="30,62 35,65 30,68" fill="#4ade80" opacity="0.7"/>
      <path d="M168 65 L180 65" stroke="#4ade80" stroke-width="2" opacity="0.6"/>
      <polygon points="178,62 183,65 178,68" fill="#4ade80" opacity="0.7"/>
      <!-- Mounting holes -->
      <circle cx="72" cy="82" r="3" fill="none" stroke="#4ade80" stroke-width="1" opacity="0.5"/>
      <circle cx="128" cy="82" r="3" fill="none" stroke="#4ade80" stroke-width="1" opacity="0.5"/>
    </svg>`,
  },
}

const DEFAULT_VISUALS = {
  grad: 'linear-gradient(135deg, #0f0f0f 0%, #1a1a2e 50%, #33336622 100%)',
  svg: `<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg">
    <circle cx="100" cy="65" r="40" fill="none" stroke="#6366f1" stroke-width="1.5" opacity="0.5"/>
    <rect x="60" y="57" width="80" height="16" rx="3" fill="#312e81" stroke="#6366f1" stroke-width="1" opacity="0.7"/>
    <rect x="40" y="60" width="22" height="10" rx="2" fill="#312e81" stroke="#6366f1" stroke-width="1" opacity="0.6"/>
    <rect x="138" y="60" width="22" height="10" rx="2" fill="#312e81" stroke="#6366f1" stroke-width="1" opacity="0.6"/>
  </svg>`,
}

function CatVisual({ slug }: { slug: string }) {
  const v = CAT_VISUALS[slug] || DEFAULT_VISUALS
  return (
    <div style={{
      height: 160,
      background: v.grad,
      borderRadius: '12px 12px 0 0',
      overflow: 'hidden',
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      {/* Subtle grid pattern */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.03) 1px, transparent 1px)',
        backgroundSize: '20px 20px',
      }} />
      {/* SVG illustration */}
      <div
        style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}
        dangerouslySetInnerHTML={{ __html: v.svg }}
      />
      {/* Bottom fade */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0, height: 40,
        background: 'linear-gradient(to top, rgba(0,0,0,0.5), transparent)',
      }} />
    </div>
  )
}

export default function HomePage() {
  const [cats, setCats] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [lang] = useLang()
  const router = useRouter()

  useEffect(() => {
    api.getCategories().then(setCats).catch(() => setCats([])).finally(() => setLoading(false))
  }, [])

  const doSearch = (e: { preventDefault: () => void }) => {
    e.preventDefault()
    if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`)
  }

  return (
    <>
      <Navbar />
      <div className="hero">
        <div className="hero-label">
          {lang === 'ua' ? 'Промисловий каталог · Tubes International' : 'Katalog przemysłowy · Tubes International'}
        </div>
        <h1>
          {lang === 'ua' ? <>Шланги, арматура<br /><em>та з&apos;єднання</em></> : <>Węże, armatura<br /><em>i złącza</em></>}
        </h1>
        <p className="hero-sub">
          {lang === 'ua' ? '189 каталогів · 46 000+ товарів · Пошук по SKU, параметрах та описі'
                         : '189 katalogów · 46 000+ produktów · Wyszukiwanie po SKU, parametrach i opisie'}
        </p>
        <form className="hero-search" onSubmit={doSearch}>
          <input
            value={q}
            onChange={(e: { target: { value: string } }) => setQ(e.target.value)}
            placeholder={t('searchPlaceholder', lang)}
          />
          <button type="submit">{t('find', lang)}</button>
        </form>
        <p className="hero-hint">
          {lang === 'ua' ? 'Підтримується: українська · польська · англійська'
                         : 'Obsługiwane: ukraiński · polski · angielski'}
        </p>
      </div>

      <div style={{ background: 'var(--bg)', padding: '56px 0' }}>
        <div className="container">
          <div className="section-header">
            <h2 className="section-title">
              {lang === 'ua' ? 'Категорії каталогу' : 'Kategorie katalogu'}
            </h2>
            <p className="section-desc">
              {lang === 'ua' ? 'Оберіть категорію для перегляду підрозділів та товарів'
                             : 'Wybierz kategorię, aby przejrzeć poddziały i produkty'}
            </p>
          </div>
          {loading ? (
            <div className="loader-wrap"><div className="spinner" /></div>
          ) : (
            <div className="cat-grid-v2">
              {cats.map((cat: Category) => (
                <Link key={cat.id} href={`/catalog/${cat.slug}`} className="cat-card-v2">
                  <CatVisual slug={cat.slug} />
                  <div className="cat-card-body">
                    <div className="cat-name-v2">{categoryName(cat.slug, lang)}</div>
                    <div className="cat-meta-v2">
                      <span>{cat.section_count} {lang === 'ua' ? 'підрозд.' : 'poddz.'}</span>
                      <span className="cat-dot">·</span>
                      <span>{cat.product_count.toLocaleString()} {lang === 'ua' ? 'товарів' : 'prod.'}</span>
                    </div>
                    <div className="cat-arrow">→</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <footer className="footer"><p>© 2025 TI-Katalog · Tubes International Україна</p></footer>
      <ChatWidget />
    </>
  )
}
