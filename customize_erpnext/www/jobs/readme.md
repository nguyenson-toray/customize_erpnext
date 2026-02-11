# Job Portal Customizations

Custom job portal for TIQN, overriding the default HRMS job listing and application experience.

## Architecture

```
www/jobs/                          # Public job listings page (no login required)
  index.py                         # Backend: queries, filters, pagination
  index.html                       # Template: hero, search, cards grid, sidebar filters
  index.js                         # Frontend: filter/search/sort/pagination, mobile drawer
  index.css                        # Styles: flat design, responsive

templates/generators/
  job_opening.html                 # Job detail page (overrides HRMS generator)

hr/web_form/job_application/       # Frappe Web Form (login_required=0)
  job_application.py               # Empty get_context (uses Frappe defaults)
  job_application.html             # Extends templates/web.html
  job_application.js               # Minimal (Frappe default behavior)

public/js/job_application_form.js  # Enhancements: file upload, validation, submit UX
public/css/job_application_form.css # Flat design for web form
```

## Loading mechanism (hooks.py)

```python
web_include_css = ["/assets/customize_erpnext/css/job_application_form.css"]
web_include_js = ["/assets/customize_erpnext/js/job_application_form.js"]
```

CSS and JS are loaded on all web pages. The JS self-activates only on `/job_application` paths.

## Guest Access

- `www/jobs/` directory is automatically public (Frappe convention)
- Web Form has `login_required=0`
- Backend uses `frappe.qb` queries that work without session user

## Design

Flat design with CSS custom properties:

| Page | Prefix | Primary Color |
|------|--------|---------------|
| Job listings | `--jp-*` | `#1e40af` |
| Job application | `--ja-*` | `#1e40af` |

Key choices:
- Solid color hero (no gradients/glassmorphism)
- `border-radius: 8px` for cards
- Cards use border-color transition only (no translateY/shadow animations)
- Custom checkboxes with `appearance: none` + `::after` checkmark for cross-browser consistency
- Company logo (`logo_white.svg`) in hero top-left corner

## Mobile Optimizations

- Sidebar filters collapse into bottom drawer on mobile
- Touch targets: 44px minimum via `@media (pointer: coarse)`
- Job application form: Frappe container padding removed on mobile to maximize content width
- Sticky "Apply Now" button on job detail page
- Full-width action buttons on mobile

## Job Listings Page (www/jobs/)

**Backend (index.py):**
- Queries published Job Openings with optional filters: company, department, employment_type
- Pagination (12 per page)
- Sort options: posting_date desc, job_title asc
- Search by job title
- Provides filter option lists (distinct companies, departments, employment types)

**Frontend (index.js):**
- URL param-based filtering (no page reload state loss)
- Search with debounced input
- Sort dropdown
- Filter count badge
- Mobile: bottom drawer for filters with apply/clear actions

## Job Detail Page (templates/generators/job_opening.html)

- Overrides HRMS default job_opening template
- Info cards: employment type, location, department, posting date, closing date
- Full job description rendered from Job Opening doctype
- "Apply Now" button links to `/job_application/new?job_title={name}`
- Inline Feather-style SVG icons (no external icon dependencies)

## Job Application Form

**Enhancements (public/js/job_application_form.js):**
- `enhanceFileUpload()` - Drag-and-drop file upload area with visual feedback
- `enhanceValidation()` - Client-side email and phone format validation
- `scrollToFirstError()` - Auto-scroll to first validation error on submit
- `enhanceSubmitButton()` - Loading spinner during submission

**Styles (public/css/job_application_form.css):**
- 2-column grid layout on desktop, single column on mobile
- Full-width fields for Text Editor, Attach, Long Text types
- Top accent line on form container
- Section heads with left border accent

**Discard/Draft button:** Uses Frappe's default behavior (no custom override).
