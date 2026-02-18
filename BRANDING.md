# MedLog Branding Guide

## Brand Identity

**Name:** MedLog
**Tagline:** Medical Conversations, Perfectly Logged

## Color Palette

### Primary Colors
- **Dark Teal:** `#3d5f5c` - Headers, text, professional tone
- **Bright Lime:** `#c5d952` - Primary actions, accents, energy

### Usage Guidelines
- **Dark Teal (#3d5f5c):**
  - Main headings (H1, H2)
  - Section card headers (default state)
  - Professional, trustworthy elements

- **Bright Lime (#c5d952):**
  - Primary buttons (Start Recording)
  - Hover states for section headers
  - Focus highlights
  - Call-to-action elements

### Hover & Interactive States
- **Section Cards:** Hover transforms teal header → lime background
- **Primary Button:** Lime background → dark teal on hover with lift effect
- **Input Focus:** Lime border with subtle glow
- **Cards:** Lift on hover with teal shadow

## Typography

**Font Stack:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif`

**Hierarchy:**
- H1 (MedLog): 2.5em, Dark Teal
- H2 (Sections): 1.8em, Dark Teal
- H3 (Cards): 1.2em, White on Teal
- Body: 1em, #333

## UI Components

### Buttons
```css
Primary (Start Recording):
- Background: #c5d952
- Text: #2c3e50
- Hover: #3d5f5c background, white text
- Effect: Lift + shadow

Danger (Stop Recording):
- Background: #e74c3c
- Hover: #c0392b
```

### Section Cards
```css
Default State:
- Header: #3d5f5c background
- Border-radius: 8px
- Shadow: Subtle gray

Hover State:
- Header: #c5d952 background with dark text
- Card lifts with teal shadow
- Smooth 0.3s transition
```

### Form Inputs
```css
Focus State:
- Border: #c5d952
- Box-shadow: Lime glow (0.1 opacity)
```

## Brand Voice

**Professional yet approachable**
- Medical accuracy and trust (Dark Teal)
- Innovation and efficiency (Bright Lime)
- Clean, modern interface
- Accessible to healthcare professionals

## Logo Integration

The company logo features:
- Circular design element (lime ring)
- Dark teal background
- Simple, memorable geometry

**Apply in UI:**
- Could be used as favicon
- Loading indicators (circular progress)
- Brand mark in header

## File Updates

### Updated Files:
1. ✅ `README.md` - Project name and references
2. ✅ `frontend/index.html` - Title and header
3. ✅ `frontend/style.css` - Complete color scheme
4. ✅ `src/main.py` - FastAPI title and logs
5. ✅ `logs/medlog.log` - Log file naming

### Color References:
- All blue (#3498db) → Teal (#3d5f5c)
- Generic green (#27ae60) → Lime (#c5d952)
- Dark headers (#2c3e50) → Teal (#3d5f5c)

## Accessibility

- Lime/Teal combination: High contrast for readability
- Dark text on lime buttons: WCAG AA compliant
- White text on teal headers: Strong contrast
- Hover states: Clear visual feedback
- Focus indicators: Visible lime highlights

---

**Version:** 1.0
**Last Updated:** February 2026
