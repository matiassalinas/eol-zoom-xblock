function EolZoomAuthorXBlock(runtime, element, settings) {
    $(function($) {
        /* If restricted access is true, start meeting through the api */
        if (settings.restricted_access) {
            start_meeting_api_url();
            $(element).find('.eolzoom_block .join_meeting-btn').attr('href', '#');
            $(element).find('.eolzoom_block .join_meeting-btn').click(join_meeting_api_url);
        } else {
            $(element).find('.eolzoom_block .start_meeting-btn').attr('href', settings.url_start_public_meeting);
        }
        
        function start_meeting_api_url() {
            // send json encoded base 64
            args = {
                'meeting_id' : settings.meeting_id,
                'course_id' : settings.course_id,
                'block_id' : settings.location
            }
            data = JSON.stringify(args)
            redirect_uri = encodeURIComponent(window.location.protocol + "//" + window.location.hostname + settings.url_start_meeting)+ "?data=" + btoa(data);
            start_meeting_url = settings.url_zoom_api + redirect_uri ;
            $(element).find('.eolzoom_block .start_meeting-btn').attr('href', start_meeting_url);
        }

        function join_meeting_api_url(e) {
            e.preventDefault(); // Cancel href: join_meeting-btn has a default url
            args = {
                "meeting_id": settings.meeting_id
            };
            $.ajax({
                url: settings.get_student_join_url,
                dataType: 'json',
                data: args,
                type: "GET",
                success: function(data){
                    if(data.status) {
                        lms_alert_redirect(data.join_url);
                        var win = window.open(data.join_url, '_blank');
                        win.focus();
                    } else {
                        console.log("ERROR: " + data.error_type);
                        lms_alert_error(data.error_type);
                    }
                }
            });
        }

        function lms_alert_error(error) {
            switch(error) {
                case 'NOT_FOUND':
                    error_message = '<strong>Aún no estás inscrito en esta sesión</strong>. Intenta nuevamente más tarde (si la videollamada ya comenzó, ponte en contacto con el equipo docente).';
                    break;
                case 'NOT_STARTED':
                    error_message = '<strong>La transmisión aún no ha comenzado</strong>. Intenta nuevamente más tarde.'
                    break;
                default:
                    error_message = 'Intenta nuevamente más tarde';
            }
            $(element).find('.eolzoom_alert').html(
                '<div class="alert alert-warning">' +
                '<p>Hubo un error al ingresar a la transmisión.</p>' +
                '<p>' + error_message + '</p>' +
                '</div>'
            ).show();

            // scroll to alert message
            $('html,body').animate({
                scrollTop: $(element).find('.eolzoom_alert').offset().top - 20
            }, 'slow');
        }

        function lms_alert_redirect(url) {

            $(element).find('.eolzoom_alert').html(
                '<div class="alert alert-info">' +
                '<p>Se abrirá una nueva pestaña con la transmisión.</p>' +
                '<p>Si aún no te redirecciona a una nueva pestaña, <a href="'+url+'" target="_blank">haz click aquí</a>.</p>' +
                '</div>'
            ).show();

            // scroll to alert message
            $('html,body').animate({
                scrollTop: $(element).find('.eolzoom_alert').offset().top - 20
            }, 'slow');
        }

    });
  
  }