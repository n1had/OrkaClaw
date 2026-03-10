export default function InputForm({ fields, values, onChange }) {
  function set(name, value) {
    onChange((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {fields.map((field) => (
        <div key={field.name} className="field">
          <label>
            {field.label}
            {field.required && <span className="req">*</span>}
          </label>

          {field.type === 'select' ? (
            <select
              value={values[field.name] || ''}
              onChange={(e) => set(field.name, e.target.value)}
            >
              <option value="">— Odaberi —</option>
              {field.options?.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : field.type === 'textarea' ? (
            <textarea
              value={values[field.name] || ''}
              onChange={(e) => set(field.name, e.target.value)}
              rows={field.name === 'forma3' ? 14 : 4}
              placeholder={field.required ? 'Obavezno polje' : 'Opcionalno'}
            />
          ) : (
            <input
              type="text"
              value={values[field.name] || ''}
              onChange={(e) => set(field.name, e.target.value)}
              placeholder={field.required ? 'Obavezno polje' : 'Opcionalno'}
            />
          )}
        </div>
      ))}
    </div>
  )
}
