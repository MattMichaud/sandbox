import streamlit as st
import streamlit.components.v1 as components

from gallery import GALLERY_DIR, delete_entry, load_gallery, publish_image
from gemini import generate_image, markdown_to_image_prompt
from plans import PLANS_DIR, extract_plan_title, format_plan_option, list_plans, load_styles


@st.fragment
def render_generate_tab():
    if "_publish_toast" in st.session_state:
        st.toast("🎨 **Published to Gallery!**", duration=3)
        del st.session_state["_publish_toast"]

    plans = list_plans()

    if not plans:
        st.warning(
            f"No plans found in `{PLANS_DIR}`. Make sure the directory exists and contains plan files."
        )
        return

    selected_plan = st.selectbox("Select a plan", plans, format_func=format_plan_option)
    st.caption(selected_plan)

    styles = load_styles()
    style = None
    if styles:
        _NO_STYLE = "No style (default)"
        chosen = st.selectbox("Artistic style", [_NO_STYLE] + styles)
        style = None if chosen == _NO_STYLE else chosen

    mode = st.radio("Image source", ["Title only", "Full markdown"], horizontal=True)

    title_strength = None
    if mode == "Full markdown":
        title_strength = st.select_slider(
            "Title strength",
            options=["Low", "Medium", "High"],
            value="Medium",
            help="How much creative weight to give the plan's filename vs. its content.",
        )

    generate = st.button("Generate", type="primary")

    if generate:
        if mode == "Title only":
            base = selected_plan.removesuffix(".md").replace("-", " ")
            title_prompt = f"{base} in the style of a {style}" if style else base
            with st.status("Generating image…") as status:
                try:
                    img_bytes = generate_image(title_prompt, status)
                    status.update(label="Done!", state="complete")
                    st.session_state.img_bytes = img_bytes
                    st.session_state.img_caption = selected_plan
                    st.session_state.img_filename = f"{selected_plan}.png"
                    st.session_state.img_prompt = title_prompt
                    st.session_state.img_mode = mode
                    st.session_state.img_plan = selected_plan
                    st.session_state.img_style = style
                except Exception as exc:
                    status.update(label="Failed", state="error")
                    st.error(f"Image generation failed: {exc}")
        else:
            markdown = (PLANS_DIR / selected_plan).read_text()
            try:
                with st.spinner("Step 1/2 — Distilling plan into image prompt…"):
                    image_prompt = markdown_to_image_prompt(
                        selected_plan, markdown, title_strength, style
                    )

                with st.status("Step 2/2 — Generating image…") as status:
                    try:
                        img_bytes = generate_image(image_prompt, status)
                        status.update(label="Done!", state="complete")
                        st.session_state.img_bytes = img_bytes
                        st.session_state.img_caption = selected_plan
                        st.session_state.img_filename = f"{selected_plan}.png"
                        st.session_state.img_prompt = image_prompt
                        st.session_state.img_mode = mode
                        st.session_state.img_plan = selected_plan
                        st.session_state.img_style = style
                    except Exception as exc:
                        status.update(label="Failed", state="error")
                        st.error(f"Image generation failed: {exc}")
            except Exception as exc:
                st.error(f"Failed: {exc}")

    if "img_bytes" in st.session_state:
        if st.session_state.img_prompt:
            with st.expander("Generated image prompt", expanded=False):
                st.write(st.session_state.img_prompt)
        st.image(st.session_state.img_bytes, caption=st.session_state.img_caption)
        st.download_button(
            label="Download PNG",
            data=st.session_state.img_bytes,
            file_name=st.session_state.img_filename,
            mime="image/png",
        )

        if st.button("Publish to Gallery", type="secondary"):
            plan_name = st.session_state.img_plan
            plan_title = extract_plan_title(plan_name)
            publish_image(
                img_bytes=st.session_state.img_bytes,
                plan_name=plan_name,
                plan_title=plan_title,
                prompt=st.session_state.img_prompt,
                mode=st.session_state.img_mode,
                style=st.session_state.get("img_style"),
            )
            st.session_state["_publish_toast"] = True
            st.rerun(scope="app")


@st.fragment
def render_gallery_tab():
    st.subheader("Gallery")
    components.html("""
<script>
(function() {
    function attachListeners() {
        var doc = window.parent.document;
        var imgs = doc.querySelectorAll('[data-testid="stImage"] img');
        imgs.forEach(function(img) {
            if (img.dataset.lightbox) return;
            img.dataset.lightbox = '1';
            img.style.cursor = 'zoom-in';
            img.addEventListener('click', function() {
                var overlay = doc.createElement('div');
                overlay.style.cssText = [
                    'position:fixed', 'inset:0', 'background:rgba(0,0,0,.85)',
                    'z-index:10000', 'display:flex', 'justify-content:center',
                    'align-items:center', 'cursor:zoom-out'
                ].join(';');
                var full = doc.createElement('img');
                full.src = this.src;
                full.style.cssText = 'max-width:90vw;max-height:90vh;object-fit:contain';
                overlay.appendChild(full);
                overlay.addEventListener('click', function() { this.remove(); });
                doc.body.appendChild(overlay);
            });
        });
    }
    attachListeners();
    setTimeout(attachListeners, 500);
    setTimeout(attachListeners, 1500);
})();
</script>
""", height=0)

    entries = load_gallery()

    if not entries:
        st.info("No published images yet. Generate an image and click \"Publish to Gallery\".")
        return

    cols = st.columns(2)
    for i, entry in enumerate(entries):
        with cols[i % 2]:
            image_path = GALLERY_DIR / entry.image_file
            st.image(str(image_path))
            st.markdown(f"**{entry.plan_title}**")
            style_suffix = f"  ·  {entry.style}" if entry.style else ""
            st.caption(entry.plan_name.removesuffix(".md") + f"  ·  {entry.mode}" + style_suffix)
            with st.expander("Image prompt"):
                st.write(entry.prompt or "")
            if st.button("Delete", key=f"delete_{entry.id}"):
                delete_entry(entry.id)
                st.rerun(scope="fragment")
