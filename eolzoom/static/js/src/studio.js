function EolZoomStudioXBlock(runtime, element, settings) {
    var handlerUrl = runtime.handlerUrl(element, 'studio_submit');
  
    $(element).find('.save-button').bind('click', function(e) {
        /*
        * Get form data and create meeting at Zoom app.
        * Update values in XBlock
        */
        var form_data = new FormData();
        var display_name = $(element).find('input[name=display_name]').val();
        var description = $(element).find('input[name=description]').val();
        var date = $(element).find('input[name=date]').val();
        var time = $(element).find('input[name=time]').val();
        var duration = $(element).find('input[name=duration]').val();
        var created_by = $(element).find('#created_by').text();
        var restricted_access = $(element).find('#restricted_access').val();
        restricted_access = restricted_access == '1';
        var google_access = $(element).find('#google_access').val();
        var youtube_permission_enabled = $(element).find('input[name=youtube_permission_enabled]').val();
        google_access = google_access == '1';
        if(display_name == "" || description == "" || date == "" || time == "" || duration < 0 || duration == "") {
            alert("Datos inválidos. Revisa nuevamente la información ingresada");
            e.preventDefault();
            return;
        }
        if(youtube_permission_enabled != "1" && google_access) {
            alert("Permisos insufiecientes con la cuenta de Google asociada");
            e.preventDefault();
            return;
        }
        form_data.append('display_name', display_name);
        form_data.append('description', description);
        form_data.append('date', date);
        form_data.append('time', time);
        form_data.append('duration', duration);
        form_data.append('created_by', created_by);
        form_data.append('meeting_id', settings.meeting_id);
        form_data.append('broadcast_id', settings.broadcast_id);
        form_data.append('restricted_access', restricted_access);
        form_data.append('google_access', google_access);

        /*
        * Set update meeting url if already have a meeting_id
        */
        if(settings.meeting_id) {
            url_meeting = settings.url_update_meeting;
        } else {
            url_meeting = settings.url_new_meeting;
        }
        if(settings.broadcast_id != "") {
            url_livebroadcast = settings.url_update_livebroadcast
        } else {
            url_livebroadcast = settings.url_new_livebroadcast
        }
        /*
        * Create or Update meeting
        */
        if ($.isFunction(runtime.notify)) {
            runtime.notify('save', {state: 'start'});
        }
        $.ajax({
            url: url_meeting,
            dataType: 'text',
            cache: false,
            contentType: false,
            processData: false,
            data: form_data,
            type: "POST",
            success: function(response){
                /*
                * Update XBlock
                */
                data = JSON.parse(response);
                if(settings.meeting_id) {
                    // If Update, set the same urls
                    form_data.set('start_url', settings.start_url);
                    form_data.set('join_url', settings.join_url);
                    form_data.set('meeting_password', settings.meeting_password);
                } else {
                    // If Create, set the urls and id
                    form_data.set('start_url', data.start_url);
                    form_data.set('join_url', data.join_url);
                    form_data.set('meeting_id', data.meeting_id);
                    form_data.set('meeting_password', data.meeting_password);
                }
                if (google_access){
                    $.ajax({
                        url: url_livebroadcast,
                        dataType: 'text',
                        cache: false,
                        contentType: false,
                        processData: false,
                        data: form_data,
                        type: "POST",
                        success: function(response){
                            data_response = JSON.parse(response)
                            if (data_response['status'] == "ok"){
                                form_data.set('broadcast_id', data_response['id_broadcast']);
                                save_form(form_data)
                            }
                            else {
                                runtime.notify('error',  {
                                    title: 'Error: Falló en Guardar',
                                    message: 'Actualice la página y reintente nuevamente, si el error persiste contáctese a eol-ayuda@uchile.cl'
                                });
                            }                            
                        }
                    });
                }
                else{
                    save_form(form_data)
                }
            }
        });

        e.preventDefault();
  
    });
    function save_form(form_data){
        $.ajax({
            url: handlerUrl,
            dataType: 'text',
            cache: false,
            contentType: false,
            processData: false,
            data: form_data,
            type: "POST",
            success: function(response){
                if ($.isFunction(runtime.notify)) {
                    runtime.notify('save', {state: 'end'});
                }
            }
        });
    }
    $(element).find('.cancel-button').bind('click', function(e) {
      runtime.notify('cancel', {});
      e.preventDefault();
    });

    $(element).find('#google_access').on('change', function() {
        //0: disabled
        //1: enabled
        if($(this).find(":selected").val()=="1"){
            $('#google_access_warning').show();
            if ($(element).find('input[name=youtube_logged]').val() == "0"){
                $('#youtube_validate_strong').hide();
            }
            if ($(element).find('input[name=youtube_logged]').val() == "1"){
                $('#youtube_validate_strong').show();
            }
        }
        if($(this).find(":selected").val()=="0"){
            $('#google_access_warning').hide();
            $('#youtube_validate_strong').hide();
        }        
      });
    $(element).find('#youtube_validate').bind('click', function(e) {
        $('#eolzoom_loading_youtube').show();
        $('#google_access_warning').hide();
        url = settings.url_youtube_validate;
        $.get(url, function(data, status){
            if(data.credentials) {
                $('#google_access').prop('disabled', false);
                aux_msg = "Sesión Iniciada.";
                $(element).find('input[name=youtube_permission_enabled]').val("1");
                $(element).find('input[name=youtube_logged]').val("1");
                if(!data.channel){
                    aux_msg = aux_msg + "</br>Cuenta no posee canal de YouTube."
                }
                if(!data.livestream){
                    aux_msg = aux_msg + "</br>Cuenta no habilitada para realizar Live en Youtube."
                }
                if(!data.livestream || !data.channel){
                    aux_msg = aux_msg + "</br><a href='https://www.youtube.com/features' >Presiona aquí</a> para verificar si está habilitada la opción 'Transmisiones en vivo incorporadas' (si tienes problemas, contacta a la mesa de ayuda de la plataforma)."
                    $(element).find('input[name=youtube_permission_enabled]').val("0");
                }
                $('#google_access_warning').html(aux_msg);
                $('#youtube_validate_strong').show();
            }
            else{
                $('#google_access').prop('disabled', true);
                actual_url = btoa(window.location.href); // encode base64
                $('#google_access_warning').html(" <a href='" + settings.url_google_auth +  "?redirect="+actual_url+"' >Vincular cuenta Google</a>");
                $(element).find('input[name=youtube_permission_enabled]').val("0");
                $(element).find('input[name=youtube_logged]').val("0");
                $('#youtube_validate_strong').hide();
            }
        }).always(function() {
            $('#eolzoom_loading_youtube').hide();
            $('#google_access_warning').show();
        });
        return false
      });
    $(function($) {
        var zoom_plan = {
            1: 'Basic',
            2: 'Licensed',
            3: 'On-prem'
        }
        // Show loading and hide elements
        $('#eolzoom_loading').show();
        $('.eolzoom_studio').hide();
        $('.eolzoom_studio li.field').hide();
        $('.save-button').hide();
        $('#eolzoom_loading_youtube').hide();
        $('#youtube_validate_strong').hide();
        check_is_logged_google();
        check_is_logged();
        get_login_url();

        if (settings.restricted_access) {
            $('#restricted_access').prop('disabled', true);
        }
        function check_is_logged() {
            /*
            * Check if user is logged at Eol Zoom API
            */
            url = settings.url_is_logged_zoom;
            $.get(url, function(user_profile, status){
                if(user_profile) {
                    // Show submit button and form whem user is succefully logged
                    $('.logging-container .zoom-login-btn').hide();
                    $('.logging-container .zoom-hint').addClass('zoom-hint-success').html("<span>Cuentas con una sesión de Zoom correctamente iniciada</span>");
                    $('.logging-container .zoom-hint').append("<br><span style='color: black;'>Tu cuenta ( <span id='created_by'>" + user_profile.email + "</span> ) tiene una licencia " + zoom_plan[user_profile.type] + "</span>");
                    $('.logging-container .zoom-hint').append("<br><span style='color: black;'>Si presentas problemas, presiona <a href='" + get_login_url() +  "' >este enlace.</a></span>");
                    if(settings.enrolled_students > 300) {
                        $('.logging-container .zoom-hint').append("<br><span style='color: #ff6422;'>Recuerda que las videollamadas tienen una capacidad máxima de <strong>300 participantes</strong>. Actualmente hay <strong>"+ settings.enrolled_students +"</strong> estudiantes inscritos en el curso.</span>");
                    }
                    /*
                    * Show content if meeting is not already created 
                    * if meeting is already created, show only if user is the owner of this meeting
                    */ 
                    if(!settings.meeting_id || (settings.created_by == user_profile.email && settings.user_id == settings.edx_created_by) ) {
                        $('.eolzoom_studio li').show();
                        $('.save-button').show();
                        // Disable restricted_access select if user doesn't have PRO PLAN
                        if(user_profile.type == 1 && !settings.restricted_access) {
                            $('#restricted_access').prop('disabled', true);
                            $('#restricted_access_warning').html("No cuentas con licencia PRO ('Licensed') por lo que se ha deshabilitado esta configuración. <a href='" + get_login_url() +  "' >Presiona aquí para obtener una licencia PRO</a> (si tienes problemas, contacta a la mesa de ayuda de la plataforma).");
                        }
                    } else {
                        $('.logging-container').html("No tienes permisos para modificar esta transmisión.");
                    }
                }
            }).always(function() {
                $('#eolzoom_loading').hide();
                $('.eolzoom_studio').show();
            });
        }

        function get_login_url() {
            /*
            * Generate login url
            */
            actual_url = btoa(window.location.href); // encode base64
            redirect_uri = encodeURIComponent(window.location.protocol + "//" + window.location.hostname + settings.url_login)+ "?redirect=" + actual_url;
            login_url = settings.url_zoom_api + redirect_uri ;
            $('.logging-container .zoom-login-btn').attr('href', login_url);
            return login_url;
        }
        
        function check_is_logged_google() {
            /*
            * Check if user is logged at Google
            */
           var is_logged = false
           url = settings.url_is_logged_google;
           $.get(url, function(data, status){
                // Show submit button and form whem user is succefully logged
                if(data.credentials) {
                    is_logged = true
                    $('#google_access').prop('disabled', false);
                    aux_msg = "Sesión Iniciada.";
                    $(element).find('input[name=youtube_permission_enabled]').val("1");
                    $(element).find('input[name=youtube_logged]').val("1");
                    if(!data.channel){
                        aux_msg = aux_msg + "</br>Cuenta no posee canal de YouTube."
                    }
                    if(!data.livestream){
                        aux_msg = aux_msg + "</br>Cuenta no habilitada para realizar Live en Youtube."
                    }
                    if(!data.livestream || !data.channel){
                        aux_msg = aux_msg + "</br><a href='https://www.youtube.com/features' >Presiona aquí</a> para verificar si está habilitada la opción 'Transmisiones en vivo incorporadas' (si tienes problemas, contacta a la mesa de ayuda de la plataforma)."
                        $(element).find('input[name=youtube_permission_enabled]').val("0");
                    }
                    $('#google_access_warning').html(aux_msg);
                    $('#youtube_validate_strong').show();
                }
                else{
                    is_logged = false
                    $('#google_access').prop('disabled', true);
                    actual_url = btoa(window.location.href); // encode base64
                    $('#google_access_warning').html(" <a href='" + settings.url_google_auth +  "?redirect="+actual_url+"' >Vincular cuenta Google</a>");
                    $(element).find('input[name=youtube_permission_enabled]').val("0");
                    $('#youtube_validate_strong').hide();
                    $(element).find('input[name=youtube_logged]').val("0");
                }
                if(settings.google_access) {
                    $('#google_access_warning').show();
                }
                else{
                    if (is_logged){
                        $('#google_access_warning').hide();
                        $('#youtube_validate_strong').hide();  
                    }
                    else{
                        $('#google_access_warning').show();
                    }
                }
            });
        }
    });
  }