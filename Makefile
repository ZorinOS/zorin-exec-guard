update-po:
	find -regex "./\(zorin_exec_guard\|desktop\).*\.\(py\|in\)" > po/POTFILES.in
	echo ./bin/zorin-exec-guard-linux >> po/POTFILES.in
	echo ./bin/zorin-exec-guard-windows >> po/POTFILES.in
	python setup.py build_i18n --merge-po --po-dir po

clean:
	rm -rf build/*

translations: po/*.po
	rm -rf build/translations
	mkdir -p build/translations/
	@for po in $^; do \
		language=`basename $$po`; \
		language=$${language%%.po}; \
		target="build/translations/$$language/LC_MESSAGES"; \
		mkdir -p $$target; \
		msgfmt --output=$$target/zorin-exec-guard.mo $$po; \
	done
